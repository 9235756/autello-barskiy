// Сборка фронтенда: две страницы (/ и /admin/), CSS — отдельными файлами.
const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = (_env, argv) => ({
  mode: argv.mode || 'production',
  entry: {
    main: './src/index.js',
    admin: './src/admin.js',
  },
  output: {
    path: path.resolve(__dirname, 'dist'),
    // contenthash в имени: nginx кеширует /assets/ на год, новая сборка = новое имя
    filename: 'assets/[name].[contenthash:8].js',
    // АБСОЛЮТНЫЙ publicPath: страница /admin/ подключает /assets/admin.css,
    // а не admin/assets/... (ошибка урока: CSS уезжал на /admin/... или /pgadmin/... → 404)
    publicPath: '/',
    clean: true,
  },
  module: {
    rules: [
      {
        test: /\.css$/i,
        // MiniCssExtractPlugin.loader, а НЕ style-loader: CSS ложится реальным файлом
        // в dist/assets/*.css и подключается <link>, а не вшивается в JS
        use: [MiniCssExtractPlugin.loader, 'css-loader'],
      },
    ],
  },
  plugins: [
    new MiniCssExtractPlugin({ filename: 'assets/[name].[contenthash:8].css' }),
    new HtmlWebpackPlugin({
      template: './src/index.html',
      filename: 'index.html',
      chunks: ['main'],
    }),
    new HtmlWebpackPlugin({
      template: './src/admin.html',
      filename: 'admin/index.html',
      chunks: ['admin'],
    }),
  ],
  devtool: false,
  performance: { hints: false },
});
