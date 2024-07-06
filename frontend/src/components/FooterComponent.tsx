import { Link } from "../RouterUtils";

const FooterComponent = () => {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="py-3 bg-gray-200 mt-auto">
      <div className="container mx-auto">
        <div className="flex justify-center border-b pb-3 mb-3">
          <div className="mr-6">
            <Link to="/" className="text-gray-600 hover:text-gray-800">
              Home
            </Link>
          </div>
          <div className="mr-6">
            <Link to="/" className="text-gray-600 hover:text-gray-800">
              FAQs
            </Link>
          </div>
          <div>
            <Link to="/" className="text-gray-600 hover:text-gray-800">
              About Us
            </Link>
          </div>
        </div>
        <p className="text-center text-gray-600">
          © <span id="currentYear">{currentYear}</span> Company, Inc
        </p>
      </div>
    </footer>
  );
};

export default FooterComponent;
