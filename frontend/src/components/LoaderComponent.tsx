const LoaderComponent = () => {
  return (
    <div className="flex flex-col items-center justify-center h-screen">
      <div className="loader"></div>
      <p className="mt-4 text-lg text-gray-300 dark:text-gray-400">
        Данные загружаются, пожалуйста, подождите...
      </p>
    </div>
  );
};

export default LoaderComponent;
