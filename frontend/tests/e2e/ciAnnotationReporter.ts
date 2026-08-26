/** Playwright reporter that emits failures as GitHub Actions annotations.
 *
 * The e2e report is uploaded as an artifact, but artifact and log downloads
 * are unreachable from some networks (Azure blob / results-receiver), which
 * reduces a red job to "Process completed with exit code 1". Annotations are
 * served by the check-runs API and render inline on the PR, so a failure is
 * diagnosable without downloading anything.
 *
 * Active only under GITHUB_ACTIONS; local runs are unaffected.
 */
import type {
  FullResult,
  Reporter,
  TestCase,
  TestResult,
} from "@playwright/test/reporter";

const ESC = (s: string) => s.replace(/\r?\n/g, "%0A").replace(/::/g, ":;");

export default class CiAnnotationReporter implements Reporter {
  private failures: string[] = [];

  onTestEnd(test: TestCase, result: TestResult): void {
    if (!process.env.GITHUB_ACTIONS) return;
    if (result.status === "passed" || result.status === "skipped") return;

    const title = test.titlePath().filter(Boolean).join(" › ");
    const where = `${test.location.file.split("/").pop()}:${test.location.line}`;
    const message = ESC(
      [
        result.error?.message ?? "",
        result.error?.snippet ?? "",
        (result.errors ?? []).map((e) => e.message ?? "").join("\n"),
      ]
        .filter(Boolean)
        .join("\n")
        .slice(0, 2500),
    );
    this.failures.push(`${title} (${where})`);
    console.log(
      `::error title=playwright ${result.status}::${ESC(title)}%0A${where}%0A${message}`,
    );
  }

  onEnd(result: FullResult): void {
    if (!process.env.GITHUB_ACTIONS) return;
    if (this.failures.length === 0) return;
    console.log(
      `::error title=playwright summary::${this.failures.length} failing test(s)%0A${ESC(
        this.failures.join("\n"),
      )}`,
    );
    void result;
  }
}
