import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
console.log(`The README posters are the generated images in ${dir}.`);
console.log("This command does not overwrite them.");
