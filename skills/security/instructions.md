# Security Skill

Use this skill for security reviews, threat checks, dependency risk, CI/CD automation, and agent workflows with tools or secrets.

Focus on:
- Trust boundaries: untrusted input, repository content, user-controlled prompts, web content, files, and comments.
- Authentication and authorization: missing checks, confused deputy paths, tenant isolation, session handling, and privilege escalation.
- Secrets: environment variables, tokens, logs, artifacts, browser storage, CI permissions, and accidental exfiltration.
- Injection: command injection, SQL/NoSQL injection, XSS, SSRF, template injection, path traversal, deserialization, and prompt injection.
- Supply chain: lockfiles, install scripts, package integrity, transitive risk, and unpinned external actions.
- Agent safety: least privilege tools, workspace trust, approval boundaries, sandboxing, and human review before destructive actions.

Return concrete risks with impact, exploit path, and mitigation. Separate confirmed issues from hypotheses. Prefer safe defaults, deny-by-default permissions, and explicit approval for irreversible changes.
