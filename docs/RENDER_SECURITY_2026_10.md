# Render security advisory assessment — 2026-11-01

## Decision and observed boundary

Rebuild and redeploy with the trust-store updates in this change. This is a
preventive remediation, not evidence of an exploit or a confirmed vulnerable
running image. Do not mark the deployed service remediated until its package
inventory and certificate rejection have been checked from the running image.

Public observations during this assessment:

- `/version` returned HTTP 200, application `0.6.0`, staging mode, commit
  `38447c2a3e665fd197e524dd8ec905c7423ad763`, and build time `unknown`.
- `/livez` and `/readyz` returned HTTP 200; readiness reported database, KB and
  API authentication ready, with DeepSeek and Groq disabled.
- GitHub main was `eca65c1a35aaca4c27580458eb376b41f6ac08bd` (2026-08-12).
  The Dockerfile, runtime requirements and Blueprint at the reported live commit
  were identical to main. The most recent listed staging workflow was from
  2026-08-12 and failed; this is not a complete Render deployment history.
- The Render dashboard required sign-in. No Render API credential or local
  container engine was available. Live image digest, build date, Debian version,
  effective environment, CA bundles and installed Python packages remain unknown.
  A commit SHA alone cannot identify the resolved image or indirect dependencies.

## Component comparison

| Component | Repository evidence | Required action |
| --- | --- | --- |
| Python | Image pinned to `3.12.11-slim` | Update within 3.12 to `3.12.16`; the October 26 release adds compromised-key rejection in `ssl`. |
| System CA store | No package refresh in Dockerfile | Install current `ca-certificates`; for the explicitly selected Debian trixie image require `20250419+deb13u1` or later. The previous live image's Debian version is unverified. |
| Application Certifi | No direct version constraint; OpenAI uses HTTPX | Require `certifi>=2026.10.19` in all three requirements entrypoints. Existing live resolution is unknown. |
| pip | Base image supplies pip; application Certifi does not update its vendored bundle | Require pip `26.2.2` or later before installing runtime dependencies. Patched Python protects the initial bootstrap. |
| MCP HTTP client | Fresh local resolution of MCP 2.0.0 uses HTTPX2 and truststore | Refresh the OS store and Python; verify this client too if its HTTPS transport is used. Local resolution does not establish the deployed version. |
| Node.js / PHP | Dockerfile builds only Python; no Node/PHP install or build step found | Their runtime-specific patches do not apply to the checked-in service build. This is source evidence, not a live process inventory. |
| Custom CA configuration | No certificate override or `verify=False` found in application source | Inspect platform environment overrides privately; do not print secrets. Update any configured custom bundle separately. |

The checked-in staging configuration disables provider calls and executor
actions. The observed readiness agrees that provider calls are disabled. This
reduces the present application's provider egress, but does not patch build-time
pip or the image's trust stores. No provider call needs to be enabled to verify TLS.

The change preserves feature flags, authentication configuration, non-root user,
entrypoint, Docker `/livez` health check and Render `/readyz` health check. It keeps
the 3.12 slim image family and explicitly selects trixie. Native wheels and
container startup still require CI verification. Direct application package pins
are otherwise unchanged; transitive dependencies remain unlocked.

## Build and deployment verification

Local validation used Python 3.12.14, not the proposed 3.12.16 container:
247 offline tests passed, the scripted failure matrix passed 17/17, and
`pip check` passed with application Certifi 2026.10.23 and pip 26.2.2
(vendored Certifi 2026.10.19). This validates dependency compatibility on the
local interpreter only; it does not validate the new Python/OS image or live TLS.
Local authenticated staging smoke passed 14/14 after preserving urllib's
case-insensitive header mapping in the smoke script. Previously, converting it
to a plain dict made the `X-Request-ID` assertion incorrectly fail for lowercase
wire header names; server behavior did not change.

CI pulls and builds without layer caching, checks Python/pip/Certifi/system-CA
versions and dependency consistency, then runs the existing container smoke.
Those checks establish the candidate image only, not Render's running image.

For a local candidate build:

```sh
docker build --pull --no-cache \
  --build-arg SUPPORT_GIT_SHA="$(git rev-parse HEAD)" \
  --build-arg SUPPORT_BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  -t support-copilot:trust-update .
```

After approval to affect the public staging service, deploy the reviewed commit
with Render's **Clear build cache & deploy** option. Record the service ID,
deploy ID, commit, image digest if exposed, and build/deploy completion times.
Retain the build log's resolved Python, pip, Certifi and system-CA versions.
Do not relax the provider/executor/auth settings. The Free service has ephemeral
SQLite storage, so deployment can reset local staging state.

From the running service shell, inspect only non-secret inventory:

```sh
cat /etc/os-release
python --version
python -m pip --version
python -m pip check
dpkg-query -W ca-certificates
python -c 'import certifi, ssl; print(certifi.__version__, certifi.where()); print(ssl.OPENSSL_VERSION, ssl.get_default_verify_paths())'
python -c 'from pip._vendor import certifi; print(certifi.__version__)'
command -v node || true
command -v php || true
```

Run the following in that same deployed container using the default HTTP clients,
without API keys. It checks a normal HTTPS control, both Render-specified test
endpoints, and the system-store path. It does not disable TLS checks or follow
redirects to other hosts. An HTTP response of any status from a test endpoint
means the client accepted the TLS connection. DNS errors, timeouts and unrelated
transport errors are inconclusive, not a pass.

```sh
python - <<'PY'
import ssl
import urllib.error
import urllib.request
import httpx
import httpx2

targets = [
    ('control', 'https://render.com/'),
    ('reject', 'https://dv-g3b-emudhra.we-have-a-problem.com/'),
    ('reject', 'https://dv-g3b-aaa-emudhra.we-have-a-problem.com/'),
]

def certificate_error(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, ssl.SSLCertVerificationError):
            return True
        exc = getattr(exc, 'reason', None) or exc.__cause__ or exc.__context__
    return False

def system_get(url):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code

failed = False
with httpx.Client(timeout=10, follow_redirects=False) as h1, \
     httpx2.Client(timeout=10, follow_redirects=False) as h2:
    clients = [('httpx', lambda url: h1.get(url).status_code),
               ('httpx2', lambda url: h2.get(url).status_code),
               ('urllib/system', system_get)]
    for name, get in clients:
        for expected, url in targets:
            try:
                status = get(url)
                passed = expected == 'control'
                result = f'TLS_ACCEPTED_HTTP_{status}'
            except Exception as exc:
                passed = expected == 'reject' and certificate_error(exc)
                result = ('CERTIFICATE_REJECTED' if certificate_error(exc)
                          else f'INCONCLUSIVE_{type(exc).__name__}')
            print(name, url, result, 'PASS' if passed else 'FAIL')
            failed |= not passed
raise SystemExit(1 if failed else 0)
PY
```

Review effective custom CA/proxy settings without exposing their values. A TLS
intercepting proxy can change which certificate is tested. Validate private
service destinations that depended on the removed roots before rollout.
Finally, check public `/version` equals the deployed commit, `/livez` and
`/readyz` succeed, and run the existing authenticated staging smoke. Health
success alone does not demonstrate rejection of compromised certificates.

## Sources

- [Render eMudhra advisory](https://render.com/docs/advisory-emudhra)
- [Render PHP2Shell advisory](https://render.com/docs/advisory-php2shell)
- [Python packaging security guidance](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576)
- [Python October 26 security releases](https://blog.python.org/2026/10/python-3152-31410-31318-31216-31118/)
- [Debian trixie fix DSA-6572-1](https://lists.debian.org/debian-security-announce/2026/msg00487.html)
- [Debian bookworm fix DLA-4845-1](https://lists.debian.org/debian-lts-announce/2026/10/msg00039.html)
- [Official Python image tags](https://github.com/docker-library/official-images/blob/master/library/python)
