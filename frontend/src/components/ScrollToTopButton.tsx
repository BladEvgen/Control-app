import { useState, useEffect, memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FaArrowUp } from "react-icons/fa";

const ScrollToTopButton: React.FC = memo(() => {
  const [isVisible, setIsVisible] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const checkFullscreen = (): boolean => {
      return (
        !!document.fullscreenElement ||
        !!(document as unknown as { webkitFullscreenElement?: Element })
          .webkitFullscreenElement ||
        !!(document as unknown as { mozFullScreenElement?: Element })
          .mozFullScreenElement ||
        !!(document as unknown as { msFullscreenElement?: Element })
          .msFullscreenElement
      );
    };

    const toggleVisibility = () => {
      const isFs = checkFullscreen();
      setIsFullscreen(isFs);
      if (window.pageYOffset > 300 && !isFs) {
        setIsVisible(true);
      } else {
        setIsVisible(false);
      }
    };

    const handleFullscreenChange = () => {
      const isFs = checkFullscreen();
      setIsFullscreen(isFs);
      if (isFs) {
        setIsVisible(false);
      } else {
        toggleVisibility();
      }
    };

    window.addEventListener("scroll", toggleVisibility);
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
    document.addEventListener("mozfullscreenchange", handleFullscreenChange);
    document.addEventListener("MSFullscreenChange", handleFullscreenChange);

    toggleVisibility();

    return () => {
      window.removeEventListener("scroll", toggleVisibility);
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      document.removeEventListener(
        "webkitfullscreenchange",
        handleFullscreenChange
      );
      document.removeEventListener("mozfullscreenchange", handleFullscreenChange);
      document.removeEventListener("MSFullscreenChange", handleFullscreenChange);
    };
  }, []);

  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  };

  if (isFullscreen) {
    return null;
  }

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.button
          initial={{ opacity: 0, scale: 0, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0, y: 20 }}
          whileHover={{ scale: 1.1, y: -2 }}
          whileTap={{ scale: 0.95 }}
          onClick={scrollToTop}
          className="hidden md:flex fixed bottom-24 right-6 z-40 p-3.5 bg-primary-600 hover:bg-primary-700 active:bg-primary-800 text-white rounded-full shadow-lg hover:shadow-xl transition-all duration-300 items-center justify-center border-2 border-white/20 dark:border-gray-800/50 backdrop-blur-sm"
          aria-label="Прокрутить наверх"
          style={{
            marginRight: "max(16px, env(safe-area-inset-right, 0px))",
            marginBottom: "env(safe-area-inset-bottom, 0px)",
          }}
        >
          <FaArrowUp className="w-4 h-4 md:w-5 md:h-5" />
        </motion.button>
      )}
    </AnimatePresence>
  );
});

ScrollToTopButton.displayName = "ScrollToTopButton";

export default ScrollToTopButton;

