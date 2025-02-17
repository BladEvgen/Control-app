import React, { useState, useRef, useEffect, useCallback } from "react";
import { Link, useNavigate } from "../RouterUtils";
import { motion, AnimatePresence } from "framer-motion";
import {
  FaBars,
  FaTimes,
  FaHome,
  FaUpload,
  FaUserClock,
  FaMoon,
  FaSun,
} from "react-icons/fa";
import { FaMapLocationDot } from "react-icons/fa6";
import { ImCamera } from "react-icons/im";
import { MdDashboard } from "react-icons/md";
import { apiUrl } from "../../apiConfig";
import { useUserContext } from "../context/UserContext";
import { logoutUser } from "../utils/authHelpers";

type MobileNavbarProps = {
  toggleTheme: () => void;
  currentTheme: string;
};

const MobileNavbar: React.FC<MobileNavbarProps> = ({
  toggleTheme,
  currentTheme,
}) => {
  const [isMenuOpen, setIsMenuOpen] = useState<boolean>(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const { user } = useUserContext();
  const username = user ? user.username : "";
  const auth = Boolean(user);

  const toggleMenu = useCallback(() => {
    setIsMenuOpen((prev) => !prev);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        isMenuOpen &&
        panelRef.current &&
        !panelRef.current.contains(event.target as Node)
      ) {
        setIsMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isMenuOpen]);

  const panelVariants = {
    hidden: { y: "100%" },
    visible: { y: 0 },
    exit: { y: "100%" },
  };

  const overlayVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 0.5 },
    exit: { opacity: 0 },
  };

  return (
    <>
      {/* Header  */}
      <header className="lg:hidden sticky top-0 z-[999] bg-primary-dark text-text-light shadow-md">
        <div className="flex items-center justify-between px-4 py-3">
          <button
            onClick={toggleMenu}
            className="text-2xl focus:outline-none active:scale-95 transition-transform"
            aria-label={isMenuOpen ? "Закрыть меню" : "Открыть меню"}
          >
            {isMenuOpen ? <FaTimes /> : <FaBars />}
          </button>
          <Link to="/" className="text-xl font-bold flex items-center">
            Staff App
            <FaUserClock className="ml-2" />
          </Link>
          <div className="w-6"></div>
        </div>
      </header>

      {/* Затемняющий фон */}
      <AnimatePresence>
        {isMenuOpen && (
          <motion.div
            className="fixed inset-0 bg-black z-[1000]"
            variants={overlayVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            transition={{ duration: 0.3 }}
            onClick={() => setIsMenuOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Панель мобильного меню */}
      <AnimatePresence>
        {isMenuOpen && (
          <motion.aside
            ref={panelRef}
            className="fixed bottom-0 left-0 right-0 z-[1001] bg-primary-dark text-text-light rounded-t-lg shadow-xl overflow-y-auto"
            variants={panelVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            transition={{ duration: 0.3, ease: "easeInOut" }}
            drag="y"
            dragConstraints={{ top: 0, bottom: 300 }}
            dragElastic={{ top: 0, bottom: 0.2 }}
            onDragEnd={(_event, info) => {
              if (info.offset.y > 100) {
                setIsMenuOpen(false);
              }
            }}
          >
            {/* Драг-хэндлер */}
            <div
              onClick={toggleMenu}
              className="py-2 border-b border-gray-700 flex justify-center cursor-pointer"
            >
              <div className="w-12 h-1 bg-gray-400 rounded-full"></div>
            </div>

            {auth && (
              <div className="px-3 py-2 border-b border-gray-700 text-lg">
                Logged in as:{" "}
                <span className="font-bold">{username || "Loading..."}</span>
              </div>
            )}

            <div className="flex flex-col justify-evenly min-h-[60vh] px-3 py-1">
              {auth ? (
                <>
                  <Link
                    to="/"
                    onClick={() => setIsMenuOpen(false)}
                    className="flex items-center px-2 py-1 hover:bg-gray-700 rounded text-lg active:scale-95 transition-transform"
                  >
                    <FaHome className="mr-2 text-blue-500" />
                    Главная
                  </Link>
                  <Link
                    to="/dashboard"
                    onClick={() => setIsMenuOpen(false)}
                    className="flex items-center px-2 py-1 hover:bg-gray-700 rounded text-lg active:scale-95 transition-transform"
                  >
                    <MdDashboard className="mr-2 text-indigo-500" />
                    Attendance
                  </Link>
                  <Link
                    to="/photo"
                    onClick={() => setIsMenuOpen(false)}
                    className="flex items-center px-2 py-1 hover:bg-gray-700 rounded text-lg active:scale-95 transition-transform"
                  >
                    <ImCamera className="mr-2 text-gray-400" />
                    Photos
                  </Link>
                  <a
                    href={`${apiUrl}/upload`}
                    onClick={() => setIsMenuOpen(false)}
                    className="flex items-center px-2 py-1 hover:bg-gray-700 rounded text-lg active:scale-95 transition-transform"
                  >
                    <FaUpload className="mr-2 text-green-500" />
                    Upload
                  </a>
                  <Link
                    to="/map"
                    onClick={() => setIsMenuOpen(false)}
                    className="flex items-center px-2 py-1 hover:bg-gray-700 rounded text-lg active:scale-95 transition-transform"
                  >
                    <FaMapLocationDot className="mr-2 text-yellow-500" />
                    Map
                  </Link>
                  <button
                    onClick={() => {
                      toggleTheme();
                      setIsMenuOpen(false);
                    }}
                    className="flex items-center w-full px-2 py-1 hover:bg-gray-700 rounded text-lg active:scale-95 transition-transform focus:outline-none"
                  >
                    {currentTheme === "dark" ? (
                      <>
                        <FaSun className="mr-2 text-yellow-500" />
                        Light Mode
                      </>
                    ) : (
                      <>
                        <FaMoon className="mr-2 text-white" />
                        Dark Mode
                      </>
                    )}
                  </button>
                  <button
                    onClick={() =>
                      logoutUser(navigate, () => setIsMenuOpen(false))
                    }
                    className="flex items-center w-full px-2 py-1 border-t border-gray-700 hover:bg-gray-700 rounded text-lg active:scale-95 transition-transform focus:outline-none mt-2 text-red-400"
                  >
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    onClick={() => setIsMenuOpen(false)}
                    className="flex items-center px-2 py-1 hover:bg-gray-700 rounded text-lg active:scale-95 transition-transform"
                  >
                    Login
                  </Link>
                  <button
                    onClick={() => {
                      toggleTheme();
                      setIsMenuOpen(false);
                    }}
                    className="flex items-center w-full px-2 py-1 hover:bg-gray-700 rounded text-lg active:scale-95 transition-transform focus:outline-none mt-2"
                  >
                    {currentTheme === "dark" ? (
                      <>
                        <FaSun className="mr-2 text-yellow-500" />
                        Light Mode
                      </>
                    ) : (
                      <>
                        <FaMoon className="mr-2 text-white" />
                        Dark Mode
                      </>
                    )}
                  </button>
                </>
              )}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
};

export default MobileNavbar;
