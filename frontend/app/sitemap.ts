import type { MetadataRoute } from "next";
import { siteUrl } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const origin = siteUrl();
  return [
    { url: origin, lastModified: new Date(), changeFrequency: "weekly", priority: 1 },
    { url: `${origin}/llms.txt`, lastModified: new Date(), changeFrequency: "weekly", priority: 0.8 },
    { url: `${origin}/llms-full.txt`, lastModified: new Date(), changeFrequency: "monthly", priority: 0.6 },
  ];
}
