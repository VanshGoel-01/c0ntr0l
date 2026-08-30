import Image from "next/image";
import { FlaskConical } from "lucide-react";

type ModelLogoProps = {
  model?: string;
  provider?: string;
  size?: number;
};

const brands = {
  deepseek: { label: "DeepSeek", src: "/model-logos/deepseek.png" },
  gemini: { label: "Google Gemini", src: "/model-logos/gemini.svg" },
  llama: { label: "Meta Llama", src: "/model-logos/llama.png" },
  microsoft: { label: "Microsoft Phi", src: "/model-logos/microsoft.png" },
  ollama: { label: "Ollama", src: "/model-logos/ollama.png" },
  qwen: { label: "Qwen", src: "/model-logos/qwen.png" },
} as const;

function resolveBrand(model = "", provider = "") {
  const value = `${model} ${provider}`.toLowerCase();
  if (value.includes("deepseek")) return brands.deepseek;
  if (value.includes("gemini") || value.includes("gemma")) return brands.gemini;
  if (value.includes("llama")) return brands.llama;
  if (value.includes("phi")) return brands.microsoft;
  if (value.includes("qwen")) return brands.qwen;
  if (value.includes("ollama")) return brands.ollama;
  return null;
}

export function ModelLogo({ model, provider, size = 30 }: ModelLogoProps) {
  const brand = resolveBrand(model, provider);
  if (!brand) return <span className="model-logo model-logo-fallback" style={{ height: size, width: size }} title="Mock model"><FlaskConical size={Math.round(size * .52)} /></span>;
  return <span className="model-logo" data-brand={brand.label.toLowerCase().replaceAll(" ", "-")} style={{ height: size, width: size }} title={`${brand.label} logo`}><Image alt="" height={size} src={brand.src} width={size} /></span>;
}
