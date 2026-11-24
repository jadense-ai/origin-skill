import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
console.log(`The README posters are the generated PNGs in ${dir}.`);
console.log("This command does not overwrite them.");
