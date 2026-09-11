import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";

const chunks = join(process.cwd(), ".next", "static", "chunks");
const files = (await readdir(chunks)).filter(name => name.endsWith(".js") || name.endsWith(".css"));
const sizes = await Promise.all(files.map(async name => ({ name, bytes: (await stat(join(chunks, name))).size })));
const js = sizes.filter(row => row.name.endsWith(".js"));
const css = sizes.filter(row => row.name.endsWith(".css"));
const totalJs = js.reduce((sum, row) => sum + row.bytes, 0);
const largestJs = Math.max(...js.map(row => row.bytes), 0);
const totalCss = css.reduce((sum, row) => sum + row.bytes, 0);
const budgets = { totalJs: 3_000_000, largestJs: 450_000, totalCss: 300_000 };
const evidence = { totalJs, largestJs, totalCss, budgets };
if (totalJs > budgets.totalJs || largestJs > budgets.largestJs || totalCss > budgets.totalCss) {
  throw new Error(`V2 production asset budget exceeded: ${JSON.stringify(evidence)}`);
}
process.stdout.write(`V2 production asset budgets: pass ${JSON.stringify(evidence)}\n`);
