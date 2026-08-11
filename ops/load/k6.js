import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: { burst: { executor: 'constant-vus', vus: 8, duration: '30s' } },
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<2000'] },
};

export default function () {
  const base = __ENV.BASE_URL;
  const token = __ENV.SUPPORT_API_TOKEN;
  const id = `K6-${__VU}-${__ITER}`;
  const response = http.post(`${base}/tickets`, JSON.stringify({
    ticket_id: id,
    ticket_text: 'How do I reset my password?',
  }), { headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` } });
  check(response, { created: (r) => r.status === 201, safe: (r) => {
    const body = r.json();
    return body.decision !== 'AUTO_REPLY' || body.grounding_safe === true;
  }});
}
