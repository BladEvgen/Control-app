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
import { logoutUser, isAuthenticated } from "../utils/authHelpers";

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
  const auth = isAuthenticated() && Boolean(user);

  const toggleMenu = useCallback(() => {
    setIsMenuOpen((prev) => !prev);
  }, []);

  useEffect(() => {
    const handleUserLoggedOut = () => {
      setIsMenuOpen(false);
    };

    window.addEventListener("userLoggedOut", handleUserLoggedOut);
    return () => {
      window.removeEventListener("userLoggedOut", handleUserLoggedOut);
    };
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
    visible: { opacity: 0.7 },
    exit: { opacity: 0 },
  };

  const menuItemVariants = {
    hidden: { opacity: 0, x: -20 },
    visible: (i: number) => ({
      opacity: 1,
      x: 0,
      transition: { delay: i * 0.05, duration: 0.3 },
    }),
  };

  const handleLogout = () => {
    logoutUser(navigate, () => setIsMenuOpen(false));
  };

  return (
    <>
      {/* Header */}
      <header className="lg:hidden sticky top-0 z-[999] bg-primary-900 dark:bg-primary-950 text-text-light shadow-md">
        <div className="flex items-center justify-between px-4 py-3">
          <button
            onClick={toggleMenu}
            className="text-2xl focus:outline-none active:scale-95 transition-transform"
            aria-label={isMenuOpen ? "Close menu" : "Open menu"}
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

      {/* Overlay background */}
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

      {/* Mobile menu panel */}
      <AnimatePresence>
        {isMenuOpen && (
          <motion.aside
            ref={panelRef}
            className="fixed bottom-0 left-0 right-0 z-[1001] bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded-t-2xl shadow-xl overflow-hidden"
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
            {/* Drag handle */}
            <div
              onClick={toggleMenu}
              className="py-2 border-b border-gray-200 dark:border-gray-800 flex justify-center cursor-pointer"
            >
              <div className="w-12 h-1 bg-gray-300 dark:bg-gray-700 rounded-full"></div>
            </div>

            {auth && (
              <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800 bg-primary-50 dark:bg-primary-900/40">
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  Logged in as
                </div>
                <div className="font-semibold text-lg text-primary-900 dark:text-primary-300">
                  {username || "Loading..."}
                </div>
              </div>
            )}

            <div className="p-4 space-y-1">
              {auth ? (
                <>
                  <motion.div
                    custom={0}
                    variants={menuItemVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <Link
                      to="/"
                      onClick={() => setIsMenuOpen(false)}
                      className="flex items-center p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <FaHome className="mr-3 text-lg text-primary-600 dark:text-primary-400" />
                      <span className="font-medium">Home</span>
                    </Link>
                  </motion.div>

                  <motion.div
                    custom={1}
                    variants={menuItemVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <Link
                      to="/dashboard"
                      onClick={() => setIsMenuOpen(false)}
                      className="flex items-center p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <MdDashboard className="mr-3 text-lg text-secondary-600 dark:text-secondary-400" />
                      <span className="font-medium">Attendance</span>
                    </Link>
                  </motion.div>

                  <motion.div
                    custom={2}
                    variants={menuItemVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <Link
                      to="/photo"
                      onClick={() => setIsMenuOpen(false)}
                      className="flex items-center p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <ImCamera className="mr-3 text-lg text-gray-600 dark:text-gray-400" />
                      <span className="font-medium">Photos</span>
                    </Link>
                  </motion.div>

                  <motion.div
                    custom={3}
                    variants={menuItemVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <a
                      href={`${apiUrl}/upload`}
                      onClick={() => setIsMenuOpen(false)}
                      className="flex items-center p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <FaUpload className="mr-3 text-lg text-success-600 dark:text-success-400" />
                      <span className="font-medium">Upload</span>
                    </a>
                  </motion.div>

                  <motion.div
                    custom={4}
                    variants={menuItemVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <Link
                      to="/map"
                      onClick={() => setIsMenuOpen(false)}
                      className="flex items-center p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <FaMapLocationDot className="mr-3 text-lg text-warning-600 dark:text-warning-400" />
                      <span className="font-medium">Map</span>
                    </Link>
                  </motion.div>

                  <motion.div
                    custom={5}
                    variants={menuItemVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <button
                      onClick={() => {
                        toggleTheme();
                        setIsMenuOpen(false);
                      }}
                      className="w-full flex items-center p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      {currentTheme === "dark" ? (
                        <>
                          <FaSun className="mr-3 text-lg text-warning-600 dark:text-warning-400" />
                          <span className="font-medium">Light Mode</span>
                        </>
                      ) : (
                        <>
                          <FaMoon className="mr-3 text-lg text-primary-900 dark:text-primary-300" />
                          <span className="font-medium">Dark Mode</span>
                        </>
                      )}
                    </button>
                  </motion.div>

                  <div className="border-t border-gray-200 dark:border-gray-800 my-2"></div>

                  <motion.div
                    custom={6}
                    variants={menuItemVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center p-3 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 text-red-600 dark:text-red-400 transition-colors"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-5 w-5 mr-3"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                        />
                      </svg>
                      <span className="font-medium">Logout</span>
                    </button>
                  </motion.div>
                </>
              ) : (
                <>
                  <motion.div
                    custom={0}
                    variants={menuItemVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <Link
                      to="/login"
                      onClick={() => setIsMenuOpen(false)}
                      className="flex items-center p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-5 w-5 mr-3 text-primary-600 dark:text-primary-400"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"
                        />
                      </svg>
                      <span className="font-medium">Login</span>
                    </Link>
                  </motion.div>

                  <motion.div
                    custom={1}
                    variants={menuItemVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <button
                      onClick={() => {
                        toggleTheme();
                        setIsMenuOpen(false);
                      }}
                      className="w-full flex items-center p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      {currentTheme === "dark" ? (
                        <>
                          <FaSun className="mr-3 text-lg text-warning-600 dark:text-warning-400" />
                          <span className="font-medium">Light Mode</span>
                        </>
                      ) : (
                        <>
                          <FaMoon className="mr-3 text-lg text-primary-900 dark:text-primary-300" />
                          <span className="font-medium">Dark Mode</span>
                        </>
                      )}
                    </button>
                  </motion.div>
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
