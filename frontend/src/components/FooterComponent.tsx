import { Link } from "../RouterUtils";

const FooterComponent = () => {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="py-4 bg-footer-light text-text-dark dark:bg-background-dark-purple dark:text-text-light mt-auto">
      <div className="container mx-auto">
        <div className="flex justify-center border-b border-text-dark dark:border-text-light pb-3 mb-3">
          <div className="mr-6">
            <Link
              to="/"
              className="text-text-dark hover:text-primary dark:text-text-light dark:hover:text-primary-light"
            >
              Home
            </Link>
          </div>
          <div className="mr-6">
            <Link
              to="/"
              className="text-text-dark hover:text-primary dark:text-text-light dark:hover:text-primary-light"
            >
              FAQs
            </Link>
          </div>
          <div>
            <Link
              to="/"
              className="text-text-dark hover:text-primary dark:text-text-light dark:hover:text-primary-light"
            >
              About Us
            </Link>
          </div>
        </div>
        <p className="text-center text-text-dark dark:text-text-light">
          © <span id="currentYear">{currentYear}</span> Company, Inc
        </p>
      </div>
    </footer>
  );
};

export default FooterComponent;
