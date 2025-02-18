import React from "react";

interface SearchInputProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  message?: string;
}

const SearchInput: React.FC<SearchInputProps> = ({
  value,
  onChange,
  message = "Поиск",
}) => {
  return (
    <input
      type="text"
      placeholder={message}
      value={value}
      onChange={onChange}
      className="
        border border-gray-300 px-4 py-2 rounded-md w-full 
        focus:outline-none focus:ring-2 focus:ring-blue-500 
        transition-colors duration-300 ease-in-out 
        dark:bg-gray-800 dark:text-white dark:border-gray-600
      "
    />
  );
};

export default SearchInput;
