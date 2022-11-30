## EJ\_PREFIX/register

### login-json
**parameters**: `login`, `password`
```
{"SID": ..., "EJSID": ...}
```

### enter-contest-json
Uses (EJ)SID received from `login-json`

**parameters**: `contest_id`
```
{"SID": ..., "EJSID": ...}
```

## EJ\_PREFIX/new-client

### contest-status-json
```
{
     "contest": {...},
     "online": {...},
     "compilers": [{"id": 2, "short_name": "gcc", "long_name": "GNU C 8.2.0", "src_sfx": ".c"}, ...],
     "problems": [{"id": 1, "short_name": "sm01-1","long_name": "a + b"}, ...]
}
```

### contest-info-json
**Doesn't work with kks auth methods.** Only token auth supported?

### session-info-json
**Doesn't work with kks auth methods.** Only token auth supported?

### problem-status-json
**parameters**: `problem` (problem ID, int)
```
{
    "problem":
    {
       "id": 25, "short_name": "...", "long_name": "...", ...
       "full_score": 50,
       "use_stdin": true, "use_stdout": true, // (unsure) always true?
       "team_enable_rep_view": true, "team_enable_ce_view": true, // report?
       "real_time_limit_ms": 5000, "time_limit_ms": 1000,
       "test_score": 0, // ?
       "run_penalty": 10,
       "compilers": [2, 57],
       "max_vm_size": "67108864",
       "is_statement_avaiable": true, "est_stmt_size": 4096 // always true? see kr01
    },
    "problem_status":
    {
       "is_viewable": false, "is_submittable": false,
       "is_tabable": true, // ?
       "is_solved": true,
       "best_run": 2, "best_score": 50,
       "all_attempts": 2,
       "eff_attempts": 1 // not IGNORED and COMPILE_ERR
    }
}
```

### problem-statement-json
**parameters**: `problem` (problem ID, int)

Returns the statement in HTML format

### list-runs-json
**parameters**: `prob_id` (int, optional)
```
{
    'runs': [
        {
            'run_id': 111,
            'prob_id': 30,
            'run_time': 1607083000,
            'status': 16,
            'passed_tests': 16,
            'score': 90
        },
        ...
    ]
}
```
newest first, if no prob\_id is passed then all runs are returned

~~Also can be retrieved by a regular session on a page with action id 301 (`NEW_SRV_ACTION_LIST_RUNS_JSON`)~~
list-runs-json is mapped to id 301. Requests from session and API are almost the same,
only auth method differs (EJSID in cookie or in query).

### run-status-json
**parameters**: `run_id` (int)
```
Ignored:
{
    "run": { ...,
        "run_id": 1, "prob_id": 1, "lang_id": 2,
        "duration": 500,
        "status": 9,
        "is_standard_problem": true, // ?
        "is_minimal_report": true
    }
}
OK:
{
    "run": {...,
        "is_with_effective_time": true, //?
        "is_src_enabled": true,
        "src_sfx": ".c", // is not set for tar.gz (sm01-3), determined by lang?
        "is_report_enabled": true, "is_report_available": true
        "is_passed_tests_available": true, "passed_tests": 5,
        "is_score_available": true, "score": 50, "score_str": "50"
    },
    "testing_report": {
        "tests": [{"num": 1, "status": 0, "time_ms": 1, "score": 0, "max_score": 0}, ...]
    }
}
```

### download-run
**parameters**: `run_id` (int)

Returns source file

Action id is 91. `submission_source` parser in `kks.ejudge` uses the same id.

### run-messages-json
**parameters**: `run_id` (int)

Comments

```
{
    'messages': [
        {
            'clar_id': 92,
            'size': 32,
            'time_us': 123456,
            'from': 0,  // judge id? 0 - hidden
            'to': 123, // user id
            'subject': '123 is commented',
            'content': {
                'method': 1, // From ejudge source: "FIXME: hard-coded base64"
                'size': 32,
                'data': 'U3ViamVjdDogMjY2IGlzIGNvbW1lbnRlZAoKdGVzdAo='  // "Subject: 123 is commented\n\ntest\n"
            }
        }
    ]
}
```

### run-test-json (not implemented)
**parameters**: `run_id`, `num`(?), `index`(?)

test inputs/outputs?

### submit-run
**parameters**: `prob_id`(int), `lang_id`(int, optional?)\
**files**: `file` (source file)
```
{"run_id": 123, "run_uuid": "..."}
```
