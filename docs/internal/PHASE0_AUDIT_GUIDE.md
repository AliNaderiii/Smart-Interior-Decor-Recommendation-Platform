# PHASE 0B - BRUTAL AUDIT GUIDE FOR V2 AGENT
**For Agent Team - Execute this exactly**

## Task 1: Dead Keys Hunt - Script Template

Create `scripts/auditDeadKeys.ts` with this logic:

```typescript
import { glob } from 'glob';
import { readFileSync } from 'fs';

const files = await glob('frontend/src/**/*.{tsx,ts}');
let dead = 0, partial = 0;
let logs: string[] = [];

for (const file of files) {
  const content = readFileSync(file, 'utf-8');
  
  // Pattern 1: Button with empty onClick or no onClick but not disabled
  // <Button>Click</Button> without onClick and not type="submit"
  const buttonRegex = /<Button(?![^>]*disabled)[^>]*>(.*?)<\/Button>/gs;
  // Also check: onClick={() => {}} or onClick={() => console.log}
  const emptyHandlerRegex = /onClick=\{.*?(console\.log|=>\s*\{\s*\}|=>\s*null).*?\}/g;
  const hashLinkRegex = /<a[^>]*href=["']#["'][^>]*>/g;
  const hrefEmptyRegex = /href=["']\s*["']/g;

  if (content.match(hashLinkRegex)) {
    logs.push(`[DEAD] ${file}: <a href="#"> found - decorative link`);
    dead++;
  }
  if (content.match(emptyHandlerRegex)) {
    const matches = [...content.matchAll(emptyHandlerRegex)];
    matches.forEach(m => {
      logs.push(`[DEAD] ${file}: empty handler ${m[0].slice(0,80)}`);
      dead++;
    });
  }

  // Pattern 2: API call without error handling
  // Look for fetch or axios without .catch or try/catch or toast.error
  if (content.includes('fetch(') || content.includes('axios.')) {
    // Simple heuristic: if file has fetch but no toast or catch, mark partial
    if (!content.includes('catch') && !content.includes('toast.error') && !content.includes('toast(')) {
      // Check if it's in a try/catch
      if (!content.match(/try\s*\{[^}]*fetch/s)) {
        logs.push(`[PARTIAL] ${file}: API call without error handling/toast`);
        partial++;
      }
    }
  }

  // Pattern 3: Button that should have modal but doesn't
  const suspiciousButtons = [
    'Add to Moodboard',
    'Export PNG',
    'Send Email',
    'Share',
    'Like',
    'Dislike',
    'Feedback'
  ];
  suspiciousButtons.forEach(btnText => {
    if (content.includes(btnText)) {
      // Check if nearby has modal or API implementation
      const idx = content.indexOf(btnText);
      const snippet = content.slice(Math.max(0, idx-500), idx+500);
      if (!snippet.includes('modal') && !snippet.includes('dialog') && !snippet.includes('api/') && !snippet.includes('POST')) {
        logs.push(`[SUSPECT] ${file}: Button "${btnText}" may lack implementation - check snippet`);
      }
    }
  });
}

console.log('=== DEAD KEYS AUDIT ===');
logs.forEach(l => console.log(l));
console.log(`\nTOTAL: ${dead} DEAD, ${partial} PARTIAL`);
if (dead > 0) {
  console.log('RESULT: FAIL - Fix all DEAD before proceeding');
  process.exit(1);
} else {
  console.log('RESULT: PASS - 0 DEAD');
}
```

**Run:** `npx tsx scripts/auditDeadKeys.ts`
**Commit result to:** `docs/AUDIT_V2.md` with sections:
- Executive Summary (X DEAD, Y PARTIAL)
- Dead Keys List (file:line, screenshot description)
- For each dead key: Fix plan (Implement vs Disable+Tooltip)

**Known suspects to check manually (from v1 codebase you built):**
1.  `ProductCard.tsx`: 
    - "Add to Moodboard" button - does it have board selection modal? Or does it assume board exists? If assumes, it's dead if no board.
    - 👍/👎 Like/Dislike - you added in P1, does it POST to /feedback? Check network tab.
    - Variant swatches - do they change image?
2.  `MoodboardEditorPage.tsx`:
    - Toolbar: "Grid/Masonry toggle", "Zoom", "Undo/Redo", "Present" - all must work or be disabled with tooltip "Coming in Phase 2"
    - "Export PNG" - implement html2canvas or mark disabled
3.  `FloorplanPage.tsx`:
    - "Export PNG", "Ruler toggle", measurement labels - check
    - Collision warning banner - does it actually calculate or always show/hide?
4.  `ShoppingListPage.tsx`:
    - Quantity stepper (+/-) - does it update total? Recalculate with useMemo?
    - "Proceed to Retailers" - does it open all links with window.open? Or copy?
5.  `Designer Dashboard`:
    - "Send Email" - is it mailto: or Resend API mock? Must copy link + toast at minimum
    - "New Project" modal - does it create project via API?
    - Share link - does copy + toast work?
6.  `Admin ProductsPage.tsx`:
    - "Sort by confidence" toggle - does sort actually work? Check useMemo sort
    - "Bulk verify" - if exists, does it call API?
    - Image zoom on hover - implemented?
7.  `Header / User Menu`:
    - Cmd+K command palette - does it exist? If not, remove trigger or implement
    - Dark mode toggle - does it toggle class and persist in localStorage?

**Fix strategy:**
- If feature is essential (Add to Moodboard, Quantity, Share copy): IMPLEMENT NOW
- If feature is delight (Export PNG, Present mode, Masonry toggle, Undo/Redo): Either implement quickly (html2canvas is 5 lines) or set `disabled={true}` + `<Tooltip>Coming in v2.1 - vote in feedback</Tooltip>`

No enabled dead button may remain.

---

## Task 2: Security Probes - Live Tests Against Running API

You said you ran probes. Document them in `docs/SECURITY_AUDIT_V2.md` with this structure:

**Run these curls against http://localhost:8000 (Postgres-backed):**

```bash
# A01 Broken Access Control - IDOR
# Login as user A (demo@smartdecor.dev), get token
TOKEN_A=$(curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"demo@smartdecor.dev","password":"Demo1234!"}' | jq -r .access_token)

# Try to access user B's project - should be 403 not 200
curl -s http://localhost:8000/projects/<id_of_designer_user_project> -H "Authorization: Bearer $TOKEN_A" -w "%{http_code}\n" -o /dev/null
# Expected: 403 or 404, not 200

# Try to access /admin/products as non-admin
curl -s http://localhost:8000/admin/products -H "Authorization: Bearer $TOKEN_A" -w "%{http_code}\n" -o /dev/null
# Expected: 403

# A02 - Check headers
curl -s -I http://localhost:8000/ | grep -i -E "strict-transport|content-security|x-frame|x-content-type|referrer|permissions"
# Log missing headers

# Check CORS
curl -s -H "Origin: https://evil.com" http://localhost:8000/auth/login -v 2>&1 | grep -i "access-control-allow-origin"
# Expected: Should be whitelist, not * (or should not echo evil.com)

# A07 - Brute force
for i in {1..6}; do
  curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"demo@smartdecor.dev","password":"wrong"}' -w "%{http_code}\n" -o /dev/null
done
# 6th should be 429

# Check JWT in cookie vs localStorage
curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"demo@smartdecor.dev","password":"Demo1234!"}' -D - -o /dev/null | grep -i set-cookie
# Expected after V2: HttpOnly, Secure, SameSite=Strict

# Check audit logs table exists
psql -c "\d audit_logs" - should show table
```

Log results in SECURITY_AUDIT_V2.md:

```
## Security Probes Results

### IDOR
- GET /projects/{other_user_id}: Got 403 as expected ✅ / Got 200 ❌ FAIL

### CORS
- Origin evil.com: Returns * ❌ FAIL / Returns allowed origin whitelist ✅

### Headers
- HSTS: Missing ❌ / Present ✅
- CSP: Missing ❌
...

### Brute Force
- 6th attempt: Got 200 ❌ FAIL / Got 429 ✅ with Retry-After header

### Cookies
- Set-Cookie HttpOnly: Missing ❌ (currently localStorage) / Present ✅ after V2 fix
```

---

## Task 3: Performance Profiling - Why it hangs

**Frontend:**

1.  `npm run build -- --report` or add `rollup-plugin-visualizer` to vite.config.ts
    - Log: Largest chunk size, which chunk contains react-grid-layout, framer-motion
    - Goal: vendor <100KB gzip, board chunk lazy loaded

2.  Chrome DevTools Performance tab (on deployed Liara, not sandbox):
    - Record drag in moodboard, check Main thread blocking
    - Look for Long Task >50ms, forced reflow (layout thrashing)
    - Log in PERF_REPORT

3.  Check images:
    - In frontend/src/pages/RecommendationsPage, check <img> vs OptimizedImage
    - Count <img> tags still using raw <img> - should be 0 after V2

**Backend:**

1.  EXPLAIN ANALYZE for recommender query:
```sql
EXPLAIN ANALYZE SELECT * FROM products WHERE price BETWEEN 1000000 AND 50000000 AND category='sofa' AND is_verified=true ORDER BY style_embedding <=> '[0.1,0.2,...]'::vector LIMIT 100;
```
- Does it use Index Scan using idx_products_price_category_verified? Does it use HNSW index for <=>?
- Log plan

2.  Check N+1 in recommender service:
- Is there loop that does DB query per product? Should be single query + python scoring

---

## Deliverables for Phase 0 Commit:

1.  `docs/RESEARCH_V2.md` - Already done (131 lines you wrote) - Expand to include 12 platforms with "What to steal"
2.  `docs/AUDIT_V2.md` - Dead keys list + perf bottlenecks + security gaps found via probes
3.  `docs/SECURITY_AUDIT_V2.md` - Table of curl probe results (IDOR, CORS, headers, brute force)
4.  `docs/PERF_REPORT_V2.md` - Bundle size, largest chunks, main thread blocking evidence

**Do not proceed to Phase 1 until these 4 files are committed. This is strict mode gate.**

After commit, tag: `git tag v2-phase0-audit && git push origin v2-phase0-audit`

Then start Phase 1 Security Hardening.

Good hunting - find every dead key.

- PM
