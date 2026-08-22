# FAQ index

Answers to the questions different teams ask when evaluating, adopting, or reviewing this
repository as a common base for marketing campaign-planning agents. Each file is written for
a specific audience; skim the one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | server-side identity, why there is no PII surface, secrets, supply chain, the audit chain, what is in vs out of scope |
| [portability-faq.md](portability-faq.md) | Architecture / cloud / exit planning | no-lock-in, the four profiles, on-prem / sovereign exit, data export |
| [features-faq.md](features-faq.md) | Product / marketing / delivery | what the agent does, what is deterministic vs LLM, and the boundary with sibling marketing and platform systems |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | rename, upstream fixes, extension points, versioning |
| [compliance-faq.md](compliance-faq.md) | Compliance / marketing governance / model risk | regulatory posture, consent, maker-checker, residency, model-risk evidence |

These FAQs deliberately do **not** re-document capabilities owned by sibling systems in the
[catalog](https://github.com/portable-genai). Where a concern belongs to
another repo (the guardrail gateway, the human-review console, the eval platform, the
marketing compliance gate, ...), the FAQ points at it and explains the boundary rather than
duplicating it. See [features-faq.md](features-faq.md) for the full "what this repo owns vs
what it integrates" map.
