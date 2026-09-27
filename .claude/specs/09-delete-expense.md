# Spec: Delete Expense

## Overview
Step 9 lets a logged-in user permanently delete one of their own expenses.
The transactions table in `profile.html` gains a "Delete" action next to the
existing "Edit" link. Because deletion is destructive and irreversible, it is
confirmed client-side before the request is sent, and performed as a `POST`
(never a bare `GET`, since the current placeholder is link-triggerable and
would let a prefetch or crawler delete data). A new `delete_expense` query
helper is added to `database/queries.py`, scoped to `id AND user_id` so a
user can never delete another user's expense.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 3: Login / Logout (`session["user_id"]` is set and enforced)
- Step 5: Profile page renders transactions (the delete action lives there)
- Step 8: Edit Expense (establishes the ownership-scoped row-mutation pattern
  this step follows: `get_expense_by_id` for ownership lookup, ownership-scoped
  `WHERE id = ? AND user_id = ?` mutations)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense if it exists and
  belongs to the current user, then redirect to `/profile` — logged-in only

No `GET` handler — the existing placeholder route accepts any method, but the
implementation must restrict this to `POST` only so the action cannot be
triggered by a plain link, prefetch, or crawler.

## Database changes
No new tables or columns. Deletion uses the existing `expenses` table
(`id`, `user_id` columns already present).

## Templates
- **Modify:** `templates/profile.html`
  - In the "Actions" table cell (currently just the "Edit" link), add a
    "Delete" control: a small `<form method="POST" action="{{ url_for('delete_expense', id=tx.id) }}">`
    with a submit button styled as a link/action, so no `GET`-triggerable
    delete link exists
  - Add an inline `onsubmit` confirmation (`return confirm('Delete this expense?')`)
    on that form, consistent with "no JS framework/bundler, vanilla JS only"

## Files to change
- `database/queries.py`
  - Add `delete_expense(expense_id, user_id)` — issues a parameterised
    `DELETE FROM expenses WHERE id = ? AND user_id = ?` for ownership safety
- `app.py`
  - Import `delete_expense` from `database.queries`
  - Replace the placeholder `delete_expense` view:
    - Restrict the route to `methods=["POST"]`
    - Redirect to `/login` if not authenticated
    - Call `get_expense_by_id(id, session["user_id"])`; `abort(404)` if
      `None` (expense doesn't exist or isn't owned by the current user)
    - Call `delete_expense(id, session["user_id"])`
    - Flash a success message (e.g. `"Expense deleted."`, category `"success"`)
    - Redirect to `url_for("profile")`
- `templates/profile.html`
  - Add the delete form/button to the "Actions" cell alongside the "Edit" link

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (n/a to this feature, but keep existing
  auth code untouched)
- `delete_expense` must scope its `DELETE` to `id = ? AND user_id = ?` so a
  user can never delete another user's expense
- Reuse `get_expense_by_id` (from Step 8) to check existence/ownership before
  deleting, rather than trusting the row-count of the `DELETE` itself — this
  keeps the 404-vs-success branching explicit and matches the edit-expense
  pattern
- The route must only accept `POST` — no `GET` handler, so the delete action
  cannot be triggered by simply visiting or prefetching a URL
- Unauthenticated access must redirect to `/login`
- If the expense does not exist or belongs to another user, return a 404
- Require a client-side confirmation (`confirm()`) before the delete form
  submits, since this is a destructive, irreversible action
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles (the delete button/form may use existing/shared classes;
  add new classes to `static/css/style.css` if needed, not `style="..."`)
- Currency must always display as ₹ — never £ or $

## Definition of done
- [ ] Visiting/posting to `/expenses/<id>/delete` while logged out redirects to `/login`
- [ ] `GET /expenses/<id>/delete` is not allowed (405, or no route match) — only `POST` works
- [ ] Posting to `/expenses/<id>/delete` for a non-existent id returns 404
- [ ] Posting to `/expenses/<id>/delete` for another user's expense returns 404 and does not delete it
- [ ] Posting to `/expenses/<id>/delete` for the current user's own expense removes it from the database
- [ ] After a successful delete, the browser is redirected to `/profile`
- [ ] The deleted expense no longer appears in the "Recent transactions" table or affects the summary stats/category breakdown
- [ ] Each row in the profile transaction table has a "Delete" action that asks for confirmation before submitting
- [ ] Clicking "Cancel" in the confirmation dialog leaves the expense untouched
