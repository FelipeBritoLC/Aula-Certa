// Testes unitários de front-end (Jest + jsdom) para os scripts de static/js.
// Ficam isolados nesta pasta para não interferir no deploy Python.
const path = require("path");

module.exports = {
  rootDir: path.resolve(__dirname, ".."),
  roots: ["<rootDir>/frontend_tests", "<rootDir>/static/js"],
  testEnvironment: require.resolve("jest-environment-jsdom"),
  testPathIgnorePatterns: ["/node_modules/"],
  collectCoverageFrom: ["static/js/**/*.js"],
  coverageDirectory: "<rootDir>/frontend_tests/coverage",
  coverageProvider: "v8",
  coverageReporters: ["text", "lcov"],
};
