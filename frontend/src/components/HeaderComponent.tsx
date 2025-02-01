import { apiUrl } from "../../apiConfig";
import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { Link, useNavigate } from "../RouterUtils";
import axiosInstance, { getCookie, setCookie, removeCookie } from "../api";
import {
  FaSignOutAlt,
  FaUpload,
  FaBars,
  FaTimes,
  FaAngleDown,
  FaUserClock,
  FaMoon,
  FaSun,
  FaHome,
} from "react-icons/fa";
import { ImCamera } from "react-icons/im";
import { FaMapLocationDot } from "react-icons/fa6";
import { MdDashboard } from "react-icons/md";
import { motion, AnimatePresence } from "framer-motion";

type HeaderComponentProps = {
  toggleTheme: () => void;
  currentTheme: string;
};

const HeaderComponent: React.FC<HeaderComponentProps> = ({
  toggleTheme,
  currentTheme,
}) => {
  const navigate = useNavigate();
  const [username, setUsername] = useState<string>(
    () => getCookie("username") || ""
  );
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => !!getCookie("access_token")
  );
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const [isStatsDropdownOpen, setIsStatsDropdownOpen] =
    useState<boolean>(false);
  const [statsMenuDirection, setStatsMenuDirection] = useState<
    "left" | "right"
  >("right");
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);

  const dropdownContainerRef = useRef<HTMLDivElement>(null);
  const statsDropdownRef = useRef<HTMLDivElement>(null);
  const statsButtonRef = useRef<HTMLButtonElement>(null);
  const profileButtonRef = useRef<HTMLButtonElement>(null);
  const mobileMenuRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  const dropdownCloseTimeoutRef = useRef<number | null>(null);
  const statsDropdownCloseTimeoutRef = useRef<number | null>(null);

  const checkAuthentication = useCallback(async () => {
    const accessToken = getCookie("access_token");
    const refreshToken = getCookie("refresh_token");

    if (accessToken && refreshToken) {
      if (!username) {
        try {
          const userDetails = await axiosInstance.get("/user/detail/");
          const fetchedUsername = userDetails.data.user.username;
          setUsername(fetchedUsername);
          setCookie("username", fetchedUsername, { path: "/" });
          setIsAuthenticated(true);
        } catch (error) {
          console.error("Ошибка при получении данных пользователя:", error);
          handleLogout();
        }
      } else {
        setIsAuthenticated(true);
      }
    } else {
      handleLogout();
    }
  }, [username]);

  const handleLogout = useCallback(() => {
    removeCookie("access_token");
    removeCookie("refresh_token");
    removeCookie("username");
    setIsAuthenticated(false);
    setUsername("");
    navigate("/login");
  }, [navigate]);

  useEffect(() => {
    checkAuthentication();
  }, [checkAuthentication]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownContainerRef.current &&
        !dropdownContainerRef.current.contains(event.target as Node)
      ) {
        setIsDropdownOpen(false);
        setIsStatsDropdownOpen(false);
      }
      if (
        isMobileMenuOpen &&
        mobileMenuRef.current &&
        !mobileMenuRef.current.contains(event.target as Node) &&
        menuButtonRef.current &&
        !menuButtonRef.current.contains(event.target as Node)
      ) {
        setIsMobileMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isMobileMenuOpen]);

  useEffect(() => {
    if (
      isStatsDropdownOpen &&
      statsButtonRef.current &&
      statsDropdownRef.current
    ) {
      const buttonRect = statsButtonRef.current.getBoundingClientRect();
      const dropdownWidth = statsDropdownRef.current.offsetWidth || 220;
      const spaceRight = window.innerWidth - buttonRect.right;
      if (spaceRight < dropdownWidth) {
        setStatsMenuDirection("left");
      } else {
        setStatsMenuDirection("right");
      }
    }
  }, [isStatsDropdownOpen]);

  const handleMouseEnter = () => {
    if (dropdownCloseTimeoutRef.current) {
      clearTimeout(dropdownCloseTimeoutRef.current);
      dropdownCloseTimeoutRef.current = null;
    }
    setIsDropdownOpen(true);
  };

  const handleMouseLeave = () => {
    dropdownCloseTimeoutRef.current = window.setTimeout(() => {
      setIsDropdownOpen(false);
      setIsStatsDropdownOpen(false);
    }, 200);
  };

  const handleStatsMouseEnter = () => {
    if (statsDropdownCloseTimeoutRef.current) {
      clearTimeout(statsDropdownCloseTimeoutRef.current);
      statsDropdownCloseTimeoutRef.current = null;
    }
    setIsStatsDropdownOpen(true);
  };

  const handleStatsMouseLeave = () => {
    statsDropdownCloseTimeoutRef.current = window.setTimeout(() => {
      setIsStatsDropdownOpen(false);
    }, 200);
  };

  const toggleMobileMenu = useCallback(() => {
    setIsMobileMenuOpen((prev) => !prev);
    setIsDropdownOpen(false);
    setIsStatsDropdownOpen(false);
  }, []);

  useEffect(() => {
    if (isMobileMenuOpen) {
      mobileMenuRef.current?.focus();
    } else {
      menuButtonRef.current?.focus();
    }
  }, [isMobileMenuOpen]);

  useEffect(() => {
    return () => {
      if (dropdownCloseTimeoutRef.current) {
        clearTimeout(dropdownCloseTimeoutRef.current);
      }
      if (statsDropdownCloseTimeoutRef.current) {
        clearTimeout(statsDropdownCloseTimeoutRef.current);
      }
    };
  }, []);

  const DropdownMenu = useMemo(
    () => (
      <AnimatePresence>
        {isDropdownOpen && (
          <motion.div
            className="absolute top-full right-0 mt-2 w-48 bg-white dark:bg-gray-800 text-gray-800 dark:text-text-light rounded-md shadow-lg z-50"
            role="menu"
            aria-label="Основное меню"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            {/* Блок подменю для Dashboard */}
            <div
              className="relative"
              onMouseEnter={handleStatsMouseEnter}
              onMouseLeave={handleStatsMouseLeave}
            >
              <button
                ref={statsButtonRef}
                className="flex items-center w-full px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 text-left rounded text-sm sm:text-base md:text-lg"
                aria-haspopup="true"
                aria-expanded={isStatsDropdownOpen}
              >
                <FaAngleDown className="mr-2" />
                Dashboards
              </button>
              <AnimatePresence>
                {isStatsDropdownOpen && (
                  <motion.div
                    ref={statsDropdownRef}
                    className={`absolute top-0 mt-0 w-56 bg-white dark:bg-gray-800 text-gray-800 dark:text-text-light rounded-md shadow-lg z-50 transition-opacity duration-200 ease-in-out ${
                      statsMenuDirection === "left"
                        ? "right-full mr-2"
                        : "left-full ml-2"
                    }`}
                    role="menu"
                    aria-label="Подменю Dashboards"
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Link to="/dashboard">
                      <button
                        onClick={() => {
                          setIsMobileMenuOpen(false);
                          setIsDropdownOpen(false);
                        }}
                        className="flex items-center px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 w-full text-left rounded text-sm sm:text-base md:text-lg"
                      >
                        {/* Допустим, тут иконка Dashboard */}
                        <MdDashboard className="mr-2 text-blue-500" />
                        Attendance
                      </button>
                    </Link>
                    <Link to="/map">
                      <button
                        onClick={() => {
                          setIsMobileMenuOpen(false);
                          setIsDropdownOpen(false);
                        }}
                        className="flex items-center px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 w-full text-left rounded text-sm sm:text-base md:text-lg"
                      >
                        <FaMapLocationDot className="mr-2 text-yellow-500" />
                        Map
                      </button>
                    </Link>
                    <Link to="/photo">
                      <button
                        onClick={() => {
                          setIsMobileMenuOpen(false);
                          setIsDropdownOpen(false);
                        }}
                        className="flex items-center px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 w-full text-left rounded text-sm sm:text-base md:text-lg"
                      >
                        <ImCamera className="mr-2 text-gray-400" />
                        Photos
                      </button>
                    </Link>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            {/* Остальные элементы основного dropdown */}
            <a href={`${apiUrl}/upload`}>
              <button
                onClick={() => setIsMobileMenuOpen(false)}
                className="flex items-center w-full px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 text-left rounded text-sm sm:text-base md:text-lg"
              >
                <FaUpload className="mr-2 text-green-500 hover:text-green-700" />
                Upload
              </button>
            </a>
            <button
              onClick={() => {
                toggleTheme();
                setIsMobileMenuOpen(false);
              }}
              className="flex items-center w-full px-4 py-3 border-t border-gray-300 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-900 text-left rounded text-sm sm:text-base md:text-lg"
            >
              {currentTheme === "dark" ? (
                <FaSun className="mr-2 text-yellow-500" />
              ) : (
                <FaMoon className="mr-2 text-gray-900" />
              )}
              {currentTheme === "dark" ? "Light Mode" : "Dark Mode"}
            </button>
            <button
              onClick={() => {
                handleLogout();
                setIsMobileMenuOpen(false);
              }}
              className="flex items-center w-full px-4 py-3 border-t border-gray-300 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-900 text-left text-red-500 rounded text-sm sm:text-base md:text-lg"
            >
              <FaSignOutAlt className="mr-2" />
              Logout
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    ),
    [
      isStatsDropdownOpen,
      statsMenuDirection,
      toggleTheme,
      currentTheme,
      handleLogout,
      statsDropdownRef,
      handleStatsMouseEnter,
      handleStatsMouseLeave,
    ]
  );

  const AuthenticatedMenu = useMemo(
    () => (
      <div
        className="relative"
        ref={dropdownContainerRef}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <button
          ref={profileButtonRef}
          className="flex items-center bg-primary hover:bg-primary-dark text-white font-bold py-2 px-4 rounded focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary text-sm sm:text-base md:text-lg"
          aria-haspopup="true"
          aria-expanded={isDropdownOpen}
        >
          <span>{username}</span>
          <FaAngleDown className="ml-2" />
        </button>
        {isDropdownOpen && DropdownMenu}
      </div>
    ),
    [DropdownMenu, isDropdownOpen, username, handleMouseEnter, handleMouseLeave]
  );

  const UnauthenticatedMenu = useMemo(
    () => (
      <div className="flex items-center space-x-4">
        <Link to="/login">
          <button className="bg-primary hover:bg-primary-dark text-white font-bold py-2 px-4 rounded text-sm sm:text-base md:text-lg">
            Login
          </button>
        </Link>
        <button
          onClick={() => {
            toggleTheme();
            setIsMobileMenuOpen(false);
          }}
          className="bg-primary hover:bg-primary-dark text-white font-bold py-2 px-4 rounded flex items-center focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary text-sm sm:text-base md:text-lg"
        >
          {currentTheme === "dark" ? (
            <FaSun className="text-yellow-500 mr-2" />
          ) : (
            <FaMoon className="text-white mr-2" />
          )}
          {currentTheme === "dark" ? "Light Mode" : "Dark Mode"}
        </button>
      </div>
    ),
    [currentTheme, toggleTheme]
  );

  const MobileMenu = useMemo(
    () => (
      <AnimatePresence>
        {isMobileMenuOpen && (
          <motion.div
            ref={mobileMenuRef}
            className="fixed top-0 left-0 z-50 w-64 bg-primary-dark text-text-light shadow-lg min-h-screen"
            initial={{ x: "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: "-100%" }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="mobile-menu-title"
            tabIndex={-1}
          >
            <div className="flex items-center justify-between p-4">
              <motion.button
                onClick={toggleMobileMenu}
                className="text-2xl text-text-light focus:outline-none"
                aria-label="Закрыть меню"
                whileTap={{ scale: 0.9 }}
              >
                <FaTimes />
              </motion.button>
            </div>
            <nav className="flex flex-col p-4 space-y-4">
              <Link
                to="/"
                onClick={() => setIsMobileMenuOpen(false)}
                className="flex items-center px-4 py-2 hover:bg-primary hover:bg-opacity-75 rounded text-left text-lg"
              >
                <FaHome className="mr-2 text-blue-500" />
                Главная
              </Link>
              <Link to="/map">
                <button
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="flex items-center px-4 py-2 hover:bg-primary hover:bg-opacity-75 rounded text-left text-lg"
                >
                  <FaMapLocationDot className="mr-2 text-yellow-500" />
                  Map
                </button>
              </Link>
              <Link to="/photo">
                <button
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="flex items-center px-4 py-2 hover:bg-primary hover:bg-opacity-75 rounded text-left text-lg"
                >
                  <ImCamera className="mr-2 text-gray-400" />
                  Photos
                </button>
              </Link>
              <a href={`${apiUrl}/upload`}>
                <button
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="flex items-center px-4 py-2 hover:bg-primary hover:bg-opacity-75 rounded text-left text-lg"
                >
                  <FaUpload className="mr-2 text-green-500 hover:text-green-700" />
                  Upload
                </button>
              </a>
              <button
                onClick={() => {
                  toggleTheme();
                  setIsMobileMenuOpen(false);
                }}
                className="flex items-center px-4 py-2 hover:bg-primary hover:bg-opacity-75 rounded text-left text-lg"
              >
                {currentTheme === "dark" ? (
                  <FaSun className="mr-2 text-yellow-500" />
                ) : (
                  <FaMoon className="mr-2 text-gray-900" />
                )}
                {currentTheme === "dark" ? "Light Mode" : "Dark Mode"}
              </button>
              <button
                onClick={() => {
                  handleLogout();
                  setIsMobileMenuOpen(false);
                }}
                className="flex items-center px-4 py-2 hover:bg-primary hover:bg-opacity-75 rounded text-left text-lg text-red-500"
              >
                <FaSignOutAlt className="mr-2" />
                Logout
              </button>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    ),
    [isMobileMenuOpen, toggleMobileMenu, currentTheme, handleLogout]
  );

  return (
    <header className="bg-primary-dark text-text-light shadow-md">
      <nav className="container mx-auto px-4 py-3 flex items-center justify-between relative">
        <div className="flex items-center lg:hidden">
          {isAuthenticated ? (
            <motion.button
              className="text-2xl sm:text-3xl text-text-light focus:outline-none"
              onClick={toggleMobileMenu}
              aria-label={isMobileMenuOpen ? "Закрыть меню" : "Открыть меню"}
              aria-expanded={isMobileMenuOpen}
              ref={menuButtonRef}
              whileTap={{ scale: 0.9 }}
              transition={{ type: "spring", stiffness: 300 }}
            >
              {isMobileMenuOpen ? <FaTimes /> : <FaBars />}
            </motion.button>
          ) : (
            UnauthenticatedMenu
          )}
        </div>
        <Link
          to="/"
          className="text-xl sm:text-2xl md:text-3xl font-bold flex items-center text-text-light"
          onClick={() => {
            if (isMobileMenuOpen) setIsMobileMenuOpen(false);
          }}
        >
          Staff App
          <FaUserClock className="ml-2 text-xl sm:text-2xl md:text-3xl" />
        </Link>
        <div className="hidden lg:flex items-center space-x-6">
          {isAuthenticated ? AuthenticatedMenu : UnauthenticatedMenu}
        </div>
      </nav>
      {MobileMenu}
    </header>
  );
};

export default HeaderComponent;
