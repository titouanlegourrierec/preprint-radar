import type { ComponentChildren } from "preact";

interface Props<T extends string> {
  /** The group's name, for screen readers ("Sort results", "Rank"). */
  legend: string;
  /** Each option's value and name. */
  options: readonly (readonly [T, string])[];
  value: T;
  onChange: (value: T) => void;
  /** An option's tooltip, where its name is not enough. */
  titles?: Partial<Record<T, string | undefined>> | undefined;
  class?: string | undefined;
  /** After the options: the relevance's ⓘ. */
  children?: ComponentChildren;
}

/**
 * One choice among a few, pressed in a row: a list's order, Rankings' kind and metric, the
 * graph's node size. The same everywhere (UX-33).
 */
export function Segmented<T extends string>(props: Props<T>) {
  return (
    <fieldset class={`segmented${props.class ? ` ${props.class}` : ""}`}>
      <legend class="visually-hidden">{props.legend}</legend>
      {props.options.map(([value, name]) => (
        <button
          key={value}
          type="button"
          class={`segmented__option${props.value === value ? " segmented__option--active" : ""}`}
          aria-pressed={props.value === value}
          title={props.titles?.[value]}
          onClick={() => props.onChange(value)}
        >
          {name}
        </button>
      ))}
      {props.children}
    </fieldset>
  );
}
