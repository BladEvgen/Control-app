import React from "react";
import { FaSearch } from "react-icons/fa";

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
    <div className="relative w-full">
      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
        <FaSearch className="h-4 w-4 text-gray-400 dark:text-gray-500" />
      </div>
      <input
        type="text"
        placeholder={message}
        value={value}
        onChange={onChange}
        className="
          w-full
          bg-white dark:bg-gray-800 
          text-gray-800 dark:text-gray-100 
          pl-10 pr-4 py-2.5 
          border border-gray-300 dark:border-gray-600 
          rounded-lg shadow-sm 
          focus:outline-none focus:ring-2 focus:ring-primary-500 dark:focus:ring-primary-600 
          focus:border-transparent
          transition-all duration-200
        "
      />
    </div>
  );
};

export default SearchInput;
