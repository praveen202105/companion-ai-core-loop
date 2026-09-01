import { randomBytes, scryptSync } from "node:crypto";

const passcode = process.argv[2];
if (!passcode || passcode.length < 8) {
  console.error("Usage: pnpm hash-passcode '<passcode with at least 8 characters>'");
  process.exit(1);
}
const salt = randomBytes(16);
const hash = scryptSync(passcode, salt, 32);
console.log(`scrypt$${salt.toString("hex")}$${hash.toString("hex")}`);
