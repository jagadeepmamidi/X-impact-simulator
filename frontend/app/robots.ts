import type { MetadataRoute } from "next";
import { siteUrl } from "@/lib/site";

const LLM_AGENTS = [
  "GPTBot",
  "ChatGPT-User",
  "OAI-SearchBot",
  "ClaudeBot",
  "anthropic-ai",
  "Claude-Web",
  "Google-Extended",
  "Googlebot",
  "GoogleOther",
  "PerplexityBot",
  "Applebot",
  "Applebot-Extended",
  "Bingbot",
  "Bytespider",
  "CCBot",
  "meta-externalagent",
  "FacebookBot",
  "Amazonbot",
  "YouBot",
  "cohere-ai",
];

export default function robots(): MetadataRoute.Robots {
  const origin = siteUrl();
  return {
    rules: [
      {
        userAgent: LLM_AGENTS,
        allow: ["/", "/llms.txt", "/llms-full.txt", "/ai.txt"],
        disallow: ["/api/"],
      },
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/"],
      },
    ],
    sitemap: `${origin}/sitemap.xml`,
    host: origin,
  };
}
