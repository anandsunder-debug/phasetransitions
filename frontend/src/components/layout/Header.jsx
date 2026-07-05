import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShoppingCart, User, Package, Leaf, Menu, X, Activity } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useCart } from '../../contexts/CartContext';
import { Button } from '../ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '../ui/dropdown-menu';

export function Header() {
  const { user, logout } = useAuth();
  const { cartCount } = useCart();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  return (
    <header className="sticky top-0 z-50 glass-header">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2" data-testid="logo-link">
            <Leaf className="w-8 h-8 text-[#2D5A27]" />
            <span className="text-xl font-bold text-[#1A1A1A] font-['Outfit']">FreshCart</span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-6">
            <Link 
              to="/products" 
              className="text-[#6B6761] hover:text-[#2D5A27] transition-colors font-medium"
              data-testid="nav-products"
            >
              Products
            </Link>
            {user && user.role === 'admin' && (
              <Link 
                to="/dashboard" 
                className="text-[#6B6761] hover:text-[#2D5A27] transition-colors font-medium flex items-center gap-1"
                data-testid="nav-dashboard"
              >
                <Activity className="w-4 h-4" />
                Dashboard
              </Link>
            )}
          </nav>

          {/* Right Actions */}
          <div className="flex items-center gap-3">
            {/* Quick Checkout — appears when cart has items */}
            {cartCount > 0 && (
              <Link to="/checkout" data-testid="quick-checkout-button">
                <Button size="sm" className="bg-[#2D5A27] hover:bg-[#1E4219] text-white rounded-full h-8 px-3 text-xs font-semibold">
                  Checkout ({cartCount})
                </Button>
              </Link>
            )}

            {/* Cart */}
            <Link to="/cart" className="relative p-2" data-testid="cart-button">
              <ShoppingCart className="w-6 h-6 text-[#1A1A1A]" />
              {cartCount > 0 && (
                <span className="cart-badge" data-testid="cart-count">{cartCount}</span>
              )}
            </Link>

            {/* User Menu */}
            {user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="rounded-full" data-testid="user-menu-button">
                    <User className="w-6 h-6" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <div className="px-2 py-1.5 text-sm font-medium">{user.name}</div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link to="/orders" className="flex items-center gap-2" data-testid="orders-link">
                      <Package className="w-4 h-4" />
                      My Orders
                    </Link>
                  </DropdownMenuItem>
                  {user.role === 'admin' && (
                    <DropdownMenuItem asChild>
                      <Link to="/dashboard" className="flex items-center gap-2" data-testid="dashboard-link">
                        <Activity className="w-4 h-4" />
                        Dashboard
                      </Link>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} data-testid="logout-button">
                    Sign Out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link to="/login">
                <Button variant="default" className="bg-[#2D5A27] hover:bg-[#1E4219] text-white" data-testid="login-button">
                  Sign In
                </Button>
              </Link>
            )}

            {/* Mobile Menu Button */}
            <button 
              className="md:hidden p-2" 
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              data-testid="mobile-menu-button"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>

        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div className="md:hidden py-4 border-t border-[#DCD7D0]">
            <nav className="flex flex-col gap-2">
              <Link 
                to="/products" 
                className="px-4 py-2 text-[#6B6761] hover:bg-[#EBE8E3] rounded-md"
                onClick={() => setMobileMenuOpen(false)}
              >
                Products
              </Link>
              {user && user.role === 'admin' && (
                <Link 
                  to="/dashboard" 
                  className="px-4 py-2 text-[#6B6761] hover:bg-[#EBE8E3] rounded-md flex items-center gap-2"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <Activity className="w-4 h-4" />
                  Dashboard
                </Link>
              )}
            </nav>
          </div>
        )}
      </div>
    </header>
  );
}
