import { SortIcon } from "./icons";

interface Props<T extends string> {
  /** What the column holds, and ranks the table by when pressed. */
  metric: T;
  /** What the table is ranked by now. */
  active: T;
  name: string;
  title?: string | undefined;
  onSort: (metric: T) => void;
}

/**
 * The header of a column of Rankings' tables (UX-42): pressed, it ranks the table by the
 * column, as the By control of the list's header does; the column ranked by says so, with
 * an arrow and `aria-sort`.
 */
export function SortHeader<T extends string>(props: Props<T>) {
  const active = props.metric === props.active;
  return (
    <th scope="col" class="rankings__number" aria-sort={active ? "descending" : undefined}>
      <button
        type="button"
        class={`rankings__sort${active ? " rankings__sort--active" : ""}`}
        title={props.title}
        onClick={() => props.onSort(props.metric)}
      >
        {props.name}
        <span class="rankings__arrow" aria-hidden="true">
          <SortIcon />
        </span>
      </button>
    </th>
  );
}
