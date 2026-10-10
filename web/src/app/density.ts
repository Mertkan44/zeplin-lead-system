import { useEffect, useState } from "react";
export type Density = "comfortable" | "compact";
export function useDensity(): [Density, (value: Density) => void] {
  const [density, setDensity] = useState<Density>(() => {
    try {
      return localStorage.getItem("zeplin_density") === "compact"
        ? "compact"
        : "comfortable";
    } catch {
      return "comfortable";
    }
  });
  useEffect(() => {
    document.documentElement.dataset.density = density;
    try {
      localStorage.setItem("zeplin_density", density);
    } catch {
      /* Preference is temporary in private mode. */
    }
  }, [density]);
  return [density, setDensity];
}
