import JavaScriptObfuscator from "javascript-obfuscator";

const { obfuscate } = JavaScriptObfuscator;

export const OBFUSCATOR_OPTIONS = {
  compact: true,
  simplify: true,

  identifierNamesGenerator: "hexadecimal",
  renameGlobals: false,
  renameProperties: false,

  stringArray: true,
  stringArrayEncoding: ["base64"],
  stringArrayThreshold: 0.75,
  stringArrayRotate: true,
  stringArrayShuffle: true,
  splitStrings: true,
  splitStringsChunkLength: 10,

  numbersToExpressions: true,
  transformObjectKeys: false,
  unicodeEscapeSequence: false,

  controlFlowFlattening: false,
  deadCodeInjection: false,
  debugProtection: false,
  disableConsoleOutput: false,
  selfDefending: false,

  target: "browser",
  sourceMap: false,
};

export default function obfuscatorPlugin(options = {}) {
  let shouldRun = options.enabled ?? false;

  return {
    name: "dqv-javascript-obfuscator",
    enforce: "post",
    apply: "build",

    configResolved(config) {
      shouldRun = options.enabled ?? config.mode === "production";
    },

    generateBundle(_outputOptions, bundle) {
      if (!shouldRun) return;

      for (const [fileName, chunk] of Object.entries(bundle)) {
        if (chunk.type !== "chunk" || !fileName.endsWith(".js")) continue;

        chunk.code = obfuscate(chunk.code, OBFUSCATOR_OPTIONS).getObfuscatedCode();
      }
    },
  };
}
