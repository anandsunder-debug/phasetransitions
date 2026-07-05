import React from 'react';
import { Link } from 'react-router-dom';
import { Leaf } from 'lucide-react';

export function Footer() {
  return (
    <footer className="bg-[#1A1A1A] text-white py-12 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="space-y-4">
            <Link to="/" className="flex items-center gap-2">
              <Leaf className="w-6 h-6 text-[#2D5A27]" />
              <span className="text-lg font-bold font-['Outfit']">FreshCart</span>
            </Link>
            <p className="text-gray-400 text-sm">
              Fresh groceries delivered to your door. Quality products, exceptional service.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="font-semibold mb-4 font-['Outfit']">Quick Links</h4>
            <ul className="space-y-2 text-sm text-gray-400">
              <li><Link to="/products" className="hover:text-white transition-colors">Products</Link></li>
              <li><Link to="/cart" className="hover:text-white transition-colors">Cart</Link></li>
              <li><Link to="/orders" className="hover:text-white transition-colors">Track Order</Link></li>
            </ul>
          </div>

          {/* Categories */}
          <div>
            <h4 className="font-semibold mb-4 font-['Outfit']">Categories</h4>
            <ul className="space-y-2 text-sm text-gray-400">
              <li><Link to="/products?category=Vegetables" className="hover:text-white transition-colors">Vegetables</Link></li>
              <li><Link to="/products?category=Fruits" className="hover:text-white transition-colors">Fruits</Link></li>
              <li><Link to="/products?category=Dairy" className="hover:text-white transition-colors">Dairy</Link></li>
              <li><Link to="/products?category=Bakery" className="hover:text-white transition-colors">Bakery</Link></li>
            </ul>
          </div>

          {/* Contact */}
          <div>
            <h4 className="font-semibold mb-4 font-['Outfit']">Contact</h4>
            <ul className="space-y-2 text-sm text-gray-400">
              <li>support@freshcart.com</li>
              <li>1-800-FRESH</li>
              <li>Mon-Sat: 8AM - 8PM</li>
            </ul>
          </div>
        </div>

        <div className="border-t border-gray-800 mt-8 pt-8 text-center text-sm text-gray-500">
          <p>&copy; {new Date().getFullYear()} FreshCart. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
