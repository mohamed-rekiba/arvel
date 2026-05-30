# Live Form Validation

Arvel's [Form Requests](requests.md) validate on every submission and return structured 422 responses. For live (as-you-type) validation, post the form fields via `fetch` and surface the errors from the standard JSON body:

```json
{
  "detail": [
    { "loc": ["body", "email"], "msg": "value is not a valid email address", "type": "value_error" }
  ]
}
```

Most SPA frameworks (Vue, React) have form libraries that accept this shape directly — see [Requests](requests.md) for the full 422 body contract.
