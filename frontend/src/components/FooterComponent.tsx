import { Link } from "../RouterUtils"; 
const FooterComponent = () => {
  const currentYear = new Date().getFullYear();

  return (
    <div className="sticky bottom-0">
      <footer className="py-3 bg-gray-200">
        <div className="container mx-auto">
          <ul className="flex justify-center border-b pb-3 mb-3">
            <li className="mr-6">
              <Link to="/" className="text-gray-600 hover:text-gray-800">
                Home
              </Link>
            </li>
            <li className="mr-6">
              <Link to="/" className="text-gray-600 hover:text-gray-800">
                FAQs
              </Link>
            </li>
            <li>
              <Link to="/" className="text-gray-600 hover:text-gray-800">
                About Us
              </Link>
            </li>
          </ul>
          <p className="text-center text-gray-600">
            ©{currentYear} Company, Inc
          </p>
        </div>
      </footer>
    </div>
  );
};

export default FooterComponent;
