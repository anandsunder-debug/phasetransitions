import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, Filter } from 'lucide-react';
import axios from 'axios';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { ProductCard } from '../components/products/ProductCard';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function ProductsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  const selectedCategory = searchParams.get('category') || 'all';

  useEffect(() => {
    const fetchData = async () => {
      // Only show loading skeleton on first load, not category switches
      if (products.length === 0) setLoading(true);
      try {
        const [productsRes, categoriesRes] = await Promise.all([
          axios.get(`${API}/products`, { 
            params: selectedCategory !== 'all' ? { category: selectedCategory } : {} 
          }),
          axios.get(`${API}/categories`)
        ]);
        setProducts(productsRes.data);
        setCategories(categoriesRes.data);
      } catch (e) {
        console.error('Failed to fetch products/categories:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [selectedCategory]); // eslint-disable-line react-hooks/exhaustive-deps

  const filteredProducts = products.filter(p =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleCategoryChange = (category) => {
    setSearchParams(category === 'all' ? {} : { category });
  };

  return (
    <div className="min-h-screen bg-[#F9F8F6]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold text-[#1A1A1A] font-['Outfit']">
            Our Products
          </h1>
          <p className="text-[#6B6761] mt-2">
            Fresh, organic groceries delivered to your door
          </p>
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-8">
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[#6B6761]" />
            <Input
              placeholder="Search products..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 bg-white border-[#DCD7D0]"
              data-testid="product-search"
            />
          </div>

          {/* Category Filters */}
          <div className="flex flex-wrap gap-2">
            <Button
              variant={selectedCategory === 'all' ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleCategoryChange('all')}
              className={selectedCategory === 'all' 
                ? 'bg-[#2D5A27] hover:bg-[#1E4219] text-white' 
                : 'border-[#DCD7D0] text-[#6B6761] hover:bg-[#EBE8E3]'
              }
              data-testid="category-all"
            >
              All
            </Button>
            {categories.map((cat) => (
              <Button
                key={cat}
                variant={selectedCategory === cat ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleCategoryChange(cat)}
                className={selectedCategory === cat 
                  ? 'bg-[#2D5A27] hover:bg-[#1E4219] text-white' 
                  : 'border-[#DCD7D0] text-[#6B6761] hover:bg-[#EBE8E3]'
                }
                data-testid={`category-${cat.toLowerCase()}`}
              >
                {cat}
              </Button>
            ))}
          </div>
        </div>

        {/* Products Grid */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {[...Array(8)].map((_, i) => (
              <div key={`skeleton-${i}`} className="bg-white rounded-md border border-[#DCD7D0] p-4 animate-pulse">
                <div className="aspect-square bg-[#EBE8E3] rounded-md mb-4" />
                <div className="h-4 bg-[#EBE8E3] rounded w-1/3 mb-2" />
                <div className="h-5 bg-[#EBE8E3] rounded w-2/3 mb-2" />
                <div className="h-4 bg-[#EBE8E3] rounded w-full" />
              </div>
            ))}
          </div>
        ) : filteredProducts.length === 0 ? (
          <div className="text-center py-16">
            <Filter className="w-12 h-12 text-[#DCD7D0] mx-auto mb-4" />
            <p className="text-[#6B6761]">No products found</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6" data-testid="products-grid">
            {filteredProducts.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
