import type { Json } from "./memory-api";

export function ContentView({ value }: { value: Json }) {
  if (value === null) return <span>Not recorded</span>;
  if (Array.isArray(value)) return <ol>{value.map((child, index) => <li key={index}><ContentView value={child} /></li>)}</ol>;
  if (typeof value === "object") {
    if (Object.keys(value).length === 1 && typeof value.text === "string") return <p className="memory-text">{value.text}</p>;
    return <dl className="memory-fields">{Object.entries(value).map(([key, child]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd><ContentView value={child} /></dd></div>)}</dl>;
  }
  return <span className="memory-text">{typeof value === "boolean" ? value ? "Yes" : "No" : String(value)}</span>;
}
