# Roadmap: the social layer

Design decisions behind `apps/social`, written before the code so the parts we
deliberately deferred are on record rather than rediscovered.

**Shipping now:** the friend graph, and "working out with a friend" — a
completed exercise clip lands on every participant's dashboard.

**Deferred:** the shared timeline, likes and comments. Nothing in this document
stubs them out. There are no empty tables and no dead columns waiting for them.
What it does is fix the three decisions that would otherwise force a rework of
the friendship model once they arrive.

---

## Decision 1 — the graph is symmetric, preferences are directional

Three concerns turn up in the same feature and want three different shapes:

| Concern | Shape | Where |
|---|---|---|
| Are A and B friends? | Symmetric: **one row per pair** | `Friendship` |
| What do *I* want from this friend? | Directional: **up to two rows per pair** | `FriendPref` |
| Who can see this thing I shared? | A property of the shared item, not the edge | (deferred) |

`Friendship` stores the pair as `user_low`/`user_high`, sorted by UUID, under a
unique constraint and a `user_low < user_high` check.

That shape earns its keep twice. "Are A and B friends" becomes one indexed
lookup instead of `Q(a=..., b=...) | Q(a=..., b=...)`, which matters because
every partner-logging call and (later) every timeline read starts with that
question. And A requesting B at the same moment B requests A cannot create two
rows — the unique constraint turns the race into an `IntegrityError` the
service catches and resolves as *mutual request implies accepted*. A
`FriendRequest(from_user, to_user)` table cannot express that invariant, and
would need application-level locking to fake it.

`FriendPref` is separate **because a preference has an owner and a friendship
does not.** "Show alice in my workout picker" is a fact about my UI, not about
the relationship; alice must not see it, change it, or be affected by it.

Today `FriendPref` holds exactly one field, `workout_partner`, which is why
putting it on `Friendship` as a boolean is so tempting — with one preference
and one feature the two designs are indistinguishable. They stop being
indistinguishable at the second preference. "Mute bob's timeline" is the
obvious next one, and adding it to a row two people share means migrating live
data from a shared row into per-side rows. Two tables now costs one extra
model; two tables later costs a data migration.

Rows are created lazily via `get_or_create` on first write. A friend you have
never configured has no `FriendPref` row, and `workout_partner=False` is the
right default for someone you have never pinned.

## Decision 2 — `workout_partner` is presentation, not permission

The Settings checkbox controls **whose chips render in my player**. It does not
grant or revoke anyone's ability to write to my log.

Write permission is: an *accepted* friendship, plus the subject's own
`allow_partner_logging`. Nothing else. In particular, alice can log a workout
to my account whether or not I have ticked her in my picker — because ticking
her is my convenience, and consenting to be logged was accepting her friend
request.

The UI says so in as many words. A checkbox that looks like a permission but
isn't is how people end up believing they are protected when they are not, and
this one sits in Settings next to real privacy switches. `test_social.py` pins
it: `workout_partner=False` must still permit logging.

## Decision 3 — blocking lives in the graph

`social.services` is the only place that decides whether two users may interact.
Blocking is enforced there, not in `apps/fitness`, so the timeline's comment
permissions inherit it for free rather than reimplementing it and drifting.

Same reasoning as the existing rule that services own the logic while routers,
MCP tools and Celery tasks stay thin — one decision, one implementation.

## Decision 4 — one user-card schema

`SocialUserOut` (`{id, username, avatar_url}`) is the only shape any API returns
for "a person who is not the caller". It already has five call sites in view:
the friends list, pending requests, the workout chips, and — later — timeline
authors and comment authors.

Defining a second user card for the timeline is the most predictable
duplication in this build, so it is named and reused from the first commit.

## Decision 5 — no cross-user reads

The friend graph grants exactly one cross-user capability: **writing an
`ExerciseEntry` to a friend's account.** It grants no reads. A friend cannot see
my entries, metrics, charts, or days.

This is narrower than it sounds and deliberately so. Health reads all run
through `DeviceEntryQuerySet.for_user()`, which filters on `created_by` and has
no concept of a friend; nothing in this feature changes that, and the deferred
timeline is what will introduce cross-user reads under its own audience model.
MCP stays self-only — the `social:*` scopes are not in the `claude` bundles.

---

## What the deferred timeline will need

Recorded here so it starts from the decisions rather than from scratch.

**A separate feed table — not `core.Event`.** `Event` is tantalisingly
feed-shaped: it already records `health.exercise.logged` with actor, verb,
target and payload. It is still the wrong source. It is an immutable audit log
whose writer swallows failures on purpose (losing an audit row beats failing a
user's request), it has no audience column, and it records things nobody should
ever see — `allow_partner_logging` being toggled, a token being minted. Reusing
it means either leaking those or bolting a privacy model onto an append-only
table. The feed gets its own `FeedItem`, written by the same service calls that
already emit events, plus a user-authored `Post`. `Event` stays the audit log.

**A three-value audience, stamped at write time.** `private | friends | public`,
resolved against the graph. Stamped onto the `FeedItem` when it is created, from
the user's per-category share settings — not filtered on read. Stamp-on-write
means changing a setting tomorrow cannot retroactively expose last month.

**`core.Visibility` is not that model.** `SHARED | PRIVATE` describes the shared
household library, and its `visible_to()` docstring — "login is the trust
boundary, so in practice everything is SHARED and every authenticated user sees
everything" — stopped being true the moment a friend graph existed. That
docstring is corrected in this body of work. The code is left alone: health rows
use `for_user()`, not `visible_to()`, and retrofitting friend-awareness into a
queryset method that runs on every query in the app is a much larger change than
the timeline needs.

**Concrete foreign keys for reactions and comments**, not `contenttypes`:
`Reaction(feed_item, user, kind)` and `Comment(feed_item, author, body, parent)`.
Generic relations would let them attach to anything, which sounds flexible and in
practice means every permission check re-derives what it is looking at.

**Fan-out on read.** Query friends' items ordered by `-occurred_at` with an
index on `(actor, occurred_at)`. With friend counts in the dozens there is no
case for materialised feed tables at any scale this project reaches self-hosted.

## Open questions

- **Notifications.** Friend requests, and later comments and partner logs, all
  want the same `Notification(user, verb, actor, target_type, target_id,
  read_at)` table. Building request notifications bespoke now means replacing
  them later; the alternative is shipping with only a nav badge.
- **Export/import** does not exist yet. When it does, friendships reference
  users by UUID that will not exist in a fresh database. Either export by
  username and re-resolve on import, or exclude the graph entirely — but decide
  it there, not by accident.
- **Single-user instances are the common case** for a self-hosted app. Every
  social surface hides itself at zero friends. Whether that also wants a hard
  kill switch (`SOCIAL_ENABLED`, or the `config.yaml` the README describes) is
  still open.
