export interface SegmentedOption {
  value: string;
  label: string;
}

interface SegmentedControlProps {
  name: string;
  value: string;
  options: SegmentedOption[];
  ariaLabel: string;
  onChange: (value: string) => void;
}

export function SegmentedControl({ name, value, options, ariaLabel, onChange }: SegmentedControlProps) {
  return (
    <div className="atlas-segmented" role="radiogroup" aria-label={ariaLabel}>
      {options.map((option) => (
        <label key={option.value}>
          <input
            checked={option.value === value}
            name={name}
            type="radio"
            value={option.value}
            onChange={() => onChange(option.value)}
          />
          <span className="atlas-segmented__option">{option.label}</span>
        </label>
      ))}
    </div>
  );
}
