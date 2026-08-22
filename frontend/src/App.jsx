import { useState } from 'react'
import './App.css'
import { LayoutDashboard, Lightbulb, Search, Settings, Menu, Bell, User } from 'lucide-react'

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Dummy data for hackathon ideas
  const ideas = [
    { id: 1, title: 'AI Study Assistant', description: 'A personalized tutor that adapts to your learning style using LLMs.', tags: ['AI', 'Education'] },
    { id: 2, title: 'Eco-Tracker App', description: 'Track your carbon footprint based on daily purchases and travel.', tags: ['Sustainability', 'Mobile'] },
    { id: 3, title: 'Smart Home Energy Optimizer', description: 'Optimizes appliance usage based on dynamic energy pricing.', tags: ['IoT', 'Green Tech'] },
    { id: 4, title: 'DevRel Analytics Dashboard', description: 'Aggregate community engagement metrics across GitHub, Discord, and Twitter.', tags: ['DevTools', 'Analytics'] },
  ]

  return (
    <div className="dashboard-container">
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <Lightbulb className="logo-icon" size={28} />
          {sidebarOpen && <h2>IdeaAgent</h2>}
        </div>
        <nav className="sidebar-nav">
          <a href="#" className="nav-item active">
            <LayoutDashboard size={20} />
            {sidebarOpen && <span>Dashboard</span>}
          </a>
          <a href="#" className="nav-item">
            <Search size={20} />
            {sidebarOpen && <span>Browse Ideas</span>}
          </a>
          <a href="#" className="nav-item">
            <Settings size={20} />
            {sidebarOpen && <span>Settings</span>}
          </a>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="topbar">
          <button className="icon-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
            <Menu size={24} />
          </button>
          <div className="topbar-right">
            <div className="search-bar">
              <Search size={18} className="search-icon" />
              <input type="text" placeholder="Search for ideas..." />
            </div>
            <button className="icon-btn"><Bell size={20} /></button>
            <button className="icon-btn"><User size={20} /></button>
          </div>
        </header>

        <div className="content-area">
          <div className="page-header">
            <h1>Hackathon Ideas Overview</h1>
            <p>Welcome to the Hackathon Ideas Browser Agent. Here are some generated ideas to get you started.</p>
          </div>

          <div className="stats-grid">
            <div className="stat-card">
              <h3>Total Ideas</h3>
              <p className="stat-value">124</p>
            </div>
            <div className="stat-card">
              <h3>Trending Topics</h3>
              <p className="stat-value">AI, IoT</p>
            </div>
            <div className="stat-card">
              <h3>Agent Status</h3>
              <p className="stat-value active-status">Online</p>
            </div>
          </div>

          <div className="ideas-grid">
            {ideas.map((idea) => (
              <div key={idea.id} className="idea-card">
                <h3>{idea.title}</h3>
                <p>{idea.description}</p>
                <div className="tags">
                  {idea.tags.map(tag => (
                    <span key={tag} className="tag">{tag}</span>
                  ))}
                </div>
                <button className="view-btn">View Details</button>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
