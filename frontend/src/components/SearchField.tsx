import { forwardRef, useRef, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FaSearch, FaTimes } from "react-icons/fa";

type SearchFieldProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  hint?: ReactNode;
};

const SearchField = forwardRef<HTMLInputElement, SearchFieldProps>(
  function SearchField({ value, onChange, placeholder, hint }, forwarded) {
    const local = useRef<HTMLInputElement | null>(null);
    return (
      <label className="ws-search">
        <FaSearch aria-hidden />
        <span className="sr-only">{placeholder}</span>
        <input
          ref={(node) => {
            local.current = node;
            if (typeof forwarded === "function") forwarded(node);
            else if (forwarded) forwarded.current = node;
          }}
          type="search"
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => event.key === "Escape" && value && onChange("")}
        />
        {hint && !value && <kbd aria-hidden>{hint}</kbd>}
        <AnimatePresence>
          {value && (
            <motion.button
              type="button"
              className="ws-search-clear"
              aria-label="Очистить поиск"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.6 }}
              transition={{ duration: 0.15 }}
              onClick={(event) => {
                event.preventDefault();
                onChange("");
                local.current?.focus();
              }}
            >
              <FaTimes aria-hidden />
            </motion.button>
          )}
        </AnimatePresence>
      </label>
    );
  },
);

export default SearchField;
