import React from "react";

interface DateInputProps {
  label: string;
  id: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  max?: string;
}

const DateInput: React.FC<DateInputProps> = ({
  label,
  id,
  value,
  onChange,
  max,
}) => (
  <div className="ws-field">
    <label htmlFor={id}>{label}</label>
    <div className="ws-input">
      <input
        type="date"
        id={id}
        value={value || ""}
        onChange={onChange}
        max={max}
      />
    </div>
  </div>
);

export default DateInput;
