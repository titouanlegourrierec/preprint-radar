import { affiliationCoverage } from "../format";
import { Attribution } from "./Attribution";
import { InfoButton } from "./InfoButton";

interface Props {
  /** The papers drawn, and those of them whose affiliations are known. */
  affiliated: number;
  total: number;
  /** "paper", or "matching paper" when words filter the graph. */
  noun: string;
  /** Where the citation counts come from and their date, for the sources line (REL-10). */
  citationsNote: string | undefined;
}

/**
 * The ⓘ button beside the legend: the notes on the data, shown on demand (UX-29) — how
 * many of the papers drawn have known affiliations (the others count for no institution,
 * PROD-16), the attribution, and the citation counts' date.
 */
export function GraphInfo({ affiliated, total, noun, citationsNote }: Props) {
  return (
    <InfoButton label="About the data" class="graph-info" above>
      <p>{`${affiliationCoverage(affiliated, total, noun)}.`}</p>
      <p>
        <Attribution />
        {citationsNote && ` ${citationsNote}.`}
      </p>
    </InfoButton>
  );
}
