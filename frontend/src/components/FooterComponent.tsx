const FooterComponent = () => {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="absolute bottom-0 left-0 right-0 py-3 bg-gray-200">
      <div className="container mx-auto">
        <ul className="flex justify-center border-b pb-3 mb-3">
          <li className="mr-6">
            <a href="/" className="text-gray-600 hover:text-gray-800">
              Home
            </a>
          </li>
          <li className="mr-6">
            <a href="#" className="text-gray-600 hover:text-gray-800">
              FAQs
            </a>
          </li>
          <li>
            <a href="/about" className="text-gray-600 hover:text-gray-800">
              About Us
            </a>
          </li>
        </ul>
        <p className="text-center text-gray-600">©{currentYear} Company, Inc</p>
      </div>
    </footer>
  );
};

export default FooterComponent;
