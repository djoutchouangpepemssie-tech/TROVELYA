import { CheckIcon } from "../icons";

type ChoiceTileProps = {
  label: string;
  pressed: boolean;
  onPressedChange: (pressed: boolean) => void;
};

/** A large toggle tile (onboarding interests): a native button with `aria-pressed`. */
export function ChoiceTile({ label, pressed, onPressedChange }: ChoiceTileProps) {
  return (
    <button
      type="button"
      className="trv-choice-tile"
      aria-pressed={pressed}
      onClick={() => {
        onPressedChange(!pressed);
      }}
    >
      <span className="trv-choice-tile-label">{label}</span>
      {pressed ? (
        <span className="trv-choice-tile-check" aria-hidden="true">
          <CheckIcon />
        </span>
      ) : null}
    </button>
  );
}
