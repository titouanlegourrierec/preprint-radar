import { countryFlag } from "../country-names";

/**
 * A country's flag before its name (UX-65), for the eye: screen readers hear the name.
 * Windows draws it as the country's letters.
 */
export function Flag({ code }: { code: string }) {
  const flag = countryFlag(code);
  return flag ? (
    <span class="flag" aria-hidden="true">
      {flag}
    </span>
  ) : null;
}
