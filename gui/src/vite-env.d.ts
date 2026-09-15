declare module '*.css';

declare module '*.svg' {
  const url: string;
  export default url;
}

// Vite fingerprints any asset a module imports, so a PNG imported here ships
// with its own hashed name as well as being emitted as a file. Declaring the
// module is what makes that import type-check: without it the TypeScript pass
// rejects the import even though the bundler resolves it.
declare module '*.png' {
  const url: string;
  export default url;
}
