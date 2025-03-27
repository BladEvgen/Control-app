import React, {
  useEffect,
  useState,
  ReactNode,
  useRef,
  useCallback,
} from "react";
import HeaderComponent from "./components/HeaderComponent";
import FooterComponent from "./components/FooterComponent";

interface LayoutProps {
  children: ReactNode;
}

const safeGetItem = (key: string, defaultValue: string): string => {
  try {
    const value = localStorage.getItem(key);
    return value !== null ? value : defaultValue;
  } catch (error) {
    console.error("Error accessing localStorage:", error);
    return defaultValue;
  }
};

const safeSetItem = (key: string, value: string): void => {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    console.error("Error setting localStorage:", error);
  }
};

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [theme, setTheme] = useState<string>(() => {
    return safeGetItem("theme", "light");
  });

  const [isChangingTheme, setIsChangingTheme] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const contentCache = useRef<ReactNode>(children);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    safeSetItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!isChangingTheme) {
      contentCache.current = children;
    }
  }, [children, isChangingTheme]);

  const toggleTheme = useCallback(() => {
    setIsChangingTheme(true);
    contentCache.current = children;

    setTimeout(() => {
      setTheme(theme === "dark" ? "light" : "dark");
      setTimeout(() => {
        setIsChangingTheme(false);
      }, 100);
    }, 50);
  }, [theme, children]);

  return (
    <div className="flex flex-col min-h-screen overflow-hidden">
      <div
        className="fixed inset-0 w-full h-full z-[-1] transition-colors duration-700"
        style={{
          background:
            theme === "dark"
              ? "linear-gradient(120deg, #0F172A 0%, #1E293B 25%, #1E3A8A 50%, #312E81 75%, #4C1D95 100%)"
              : "linear-gradient(120deg, #F9FAFB 0%, #F3F4F6 25%, #EFF6FF 50%, #F5F3FF 75%, #FAF5FF 100%)",
        }}
      />

      <HeaderComponent toggleTheme={toggleTheme} currentTheme={theme} />

      <main className="flex-1 relative pt-6 pb-10">
        <div
          ref={contentRef}
          className="relative z-10 container mx-auto px-4 transition-opacity duration-300"
          style={{ opacity: isChangingTheme ? 0.6 : 1 }}
        >
          {isChangingTheme && contentCache.current
            ? contentCache.current
            : children}
        </div>
      </main>

      <FooterComponent />
    </div>
  );
};

export default Layout;
