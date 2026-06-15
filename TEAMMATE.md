# Project 5 - status update

The crawl logic is done. The four `TODO` methods in `4700crawler` are
implemented and the parsers are smoke-tested locally. Network half (yours)
was untouched.

## What's now done (my half)

All in `4700crawler`. Only `html.parser` and `urllib.parse` were added on top
of what was already there - no HTTP/cookies libs.

### `login()`
- GETs `LOGIN_PATH` so the client picks up the `csrftoken` cookie.
- Parses the hidden `csrfmiddlewaretoken` out of the form with a small
  `HTMLParser` (`_find_csrf_token`).
- POSTs `username`, `password`, `csrfmiddlewaretoken`, `next=/fakebook/`
  with a same-origin `Referer` header. **Note:** Django's HTTPS CSRF check
  rejects POSTs without a matching `Referer`, so I add it explicitly via
  `extra_headers={"Referer": "https://<server>/accounts/login/?next=/fakebook/"}`.
  If that header isn't being set on the request that's the first thing to check.
- Follows up to 10 redirects after the POST, then asserts we have a `sessionid`
  cookie + a 200. Raises `RuntimeError` with the status/cookie state otherwise.

### `extract_links(html)`
- `_LinkParser` (subclass of `html.parser.HTMLParser`) grabs every `<a href>`.
- `_normalize_link` filters:
  - rejects foreign hosts (compares both `netloc` and `hostname` against
    `self.server`),
  - keeps relative paths (empty `netloc`),
  - keeps only paths starting with `/fakebook/`,
  - strips fragment, preserves query string.
- Returns a list of paths (no full URLs).

### `extract_flags(html)`
- `_FlagParser` looks for `<h3>` whose `class` attribute contains
  `secret_flag` (split on whitespace, so extra classes are tolerated).
- Buffers text between start/end tag, strips the `FLAG: ` prefix, returns
  the 64-char body.

### `crawl()`
- Pops paths off `self.frontier` (LIFO - fine for our purposes; switch to
  `popleft()` from a `deque` if we want BFS later).
- Skips anything in `self.visited`.
- Branches on status:
  - `200` -> `extract_flags` + `extract_links`, dedupes flags, appends
    unseen links to the frontier. Early-returns when 5 flags are collected.
  - `301`/`302` -> normalize `Location` via `_normalize_link` and requeue
    if it's in-domain and unseen.
  - `403`/`404` -> drop.
  - Anything else -> drop (503 is retried inside the client).
- `OSError`/`ConnectionError` is treated as transient: it un-marks the path
  as visited and requeues it.

### Helpers added at module level
- `_LinkParser`, `_FlagParser` - `html.parser` subclasses.
- `_find_csrf_token(html)` - returns the hidden form token value or `None`.
- `_path_from_location(location)` - normalizes absolute or relative `Location`
  headers down to the path+query our client wants.

## How I tested

Locally only - I don't have a Northeastern login, so this hasn't hit the real
Fakebook yet. What I did run:

- Loaded `4700crawler` as a module and fed sample HTML through
  `extract_links` / `extract_flags` / `_find_csrf_token` /
  `_path_from_location`. All four returned what they should:
  - external host (`google.com`) dropped, in-domain absolute and relative
    `/fakebook/...` kept, non-`/fakebook/` (`/accounts/logout/`) dropped,
    bare `#anchor` dropped.
  - two flags parsed out cleanly, `FLAG: ` prefix stripped, 64 chars preserved.
  - hidden CSRF input value returned.
  - both absolute and relative `Location` strings collapse to the same path.

That's all I can verify without the real server.

## Still pending (let's do together)

1. **Real run against Fakebook** - we need your or my Northeastern credentials
   to actually log in and confirm the 5 flags come back. If the login 403s,
   the most likely cause is the `Referer` header path - it's hardcoded to
   `LOGIN_PATH`, which should be fine, but worth double-checking against what
   Chrome devtools shows on a real login.
2. **`secret_flags` file** - 10 lines (5 of yours, 5 of mine) once we've both
   run the crawler.
3. **`README.md`** - approach, challenges, testing. I'll draft once we've
   confirmed the crawler works end-to-end.

## Things to sanity-check on the first real run

- Does the first GET to `LOGIN_PATH` actually populate `csrftoken` in the
  cookie jar? If `client.get_cookie('csrftoken')` is `None` after the GET,
  the cookie parser in `http_client.py` may need to handle a multi-cookie
  `Set-Cookie` header (it currently splits on `;` and keeps the first pair,
  which is the standard format - should be fine, but watch for it).
- Does the POST come back as a 302 with `sessionid` in `Set-Cookie`? If we
  get 200 back with the login form re-rendered, CSRF likely failed - check
  the `Referer` header and that we're sending the `csrftoken` cookie *and*
  the form token together.
- Crawler termination: it stops on `len(self.flags) >= 5`. If we somehow
  finish the frontier without 5 flags, `run()` will just print however many
  we got. Watch for that case.

## Run it

```bash
make
./4700crawler <username> <password>
```

Prints exactly the 5 flags, one per line, nothing else.
