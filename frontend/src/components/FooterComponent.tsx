import { motion } from "framer-motion";
import { Link } from "../RouterUtils";
import {
  FaSpotify,
  FaInstagram,
  FaTelegramPlane,
  FaGithub,
} from "react-icons/fa";

const FooterComponent = () => {
  const currentYear = new Date().getFullYear();

  return (
    <motion.footer
      className="py-6 text-text-dark dark:text-text-light"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, ease: "easeOut" }}
    >
      <div className="container mx-auto px-4">
        {/* Навигационные ссылки */}
        <div className="flex flex-col md:flex-row justify-center items-center border-b border-text-dark dark:border-text-light pb-4 mb-4">
          <div className="mr-0 md:mr-6 mb-2 md:mb-0">
            <Link
              to="/"
              className="flex items-center text-text-dark dark:text-text-light hover:text-primary dark:hover:text-accent-light transition-colors duration-300"
            >
              <i className="fas fa-home mr-2"></i> Home
            </Link>
          </div>
          <div className="mr-0 md:mr-6 mb-2 md:mb-0">
            <a
              href="https://new.krmu.edu.kz"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center text-text-dark dark:text-text-light hover:text-primary dark:hover:text-accent-light transition-colors duration-300"
            >
              <i className="fas fa-question-circle mr-2"></i> KRMU
            </a>
          </div>
          <div>
            <a
              href="https://new.krmu.edu.kz/О_нас/Об_университете/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center text-text-dark dark:text-text-light hover:text-primary dark:hover:text-accent-light transition-colors duration-300"
            >
              <i className="fas fa-info-circle mr-2"></i> About Us
            </a>
          </div>
        </div>

        {/* Социальные ссылки */}
        <div className="flex justify-center space-x-6 mb-4">
          <motion.a
            href="https://open.spotify.com/playlist/6msWJa9K9ul2m5UasXjTRb?si=2b1aea17fe2d4267"
            target="_blank"
            rel="noopener noreferrer"
            className="text-text-dark dark:text-text-light hover:text-primary dark:hover:text-accent-light transition-colors duration-300"
            whileHover={{ scale: 1.1 }}
          >
            <FaSpotify size={20} />
          </motion.a>
          <motion.a
            href="https://www.instagram.com/bladevgen"
            target="_blank"
            rel="noopener noreferrer"
            className="text-text-dark dark:text-text-light hover:text-primary dark:hover:text-accent-light transition-colors duration-300"
            whileHover={{ scale: 1.1 }}
          >
            <FaInstagram size={20} />
          </motion.a>
          <motion.a
            href="https://t.me/bladevgen"
            target="_blank"
            rel="noopener noreferrer"
            className="text-text-dark dark:text-text-light hover:text-primary dark:hover:text-accent-light transition-colors duration-300"
            whileHover={{ scale: 1.1 }}
          >
            <FaTelegramPlane size={20} />
          </motion.a>
        </div>

        {/* Ссылка на разработчика */}
        <div className="flex justify-center mb-4">
          <motion.a
            href="https://github.com/bladEvgen"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center text-text-dark dark:text-text-light hover:text-primary dark:hover:text-accent-light transition-colors duration-300"
            whileHover={{ scale: 1.05 }}
          >
            <FaGithub size={20} className="mr-2" />
            Developed by bladEvgen
          </motion.a>
        </div>

        {/* Копирайт с MIT License */}
        <motion.p
          className="text-center text-sm"
          whileHover={{ scale: 1.02 }}
          transition={{ duration: 0.3 }}
        >
          © {currentYear} Company, Inc. •{" "}
          <a
            href="https://opensource.org/licenses/MIT"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-primary dark:hover:text-accent-light transition-colors duration-300"
          >
            MIT License
          </a>
        </motion.p>
      </div>
    </motion.footer>
  );
};

export default FooterComponent;
