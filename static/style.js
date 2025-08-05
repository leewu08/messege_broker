.user-dropdown {
  position: relative;
  display: inline-block;
}

.user-dropdown-content {
  display: none;
  position: absolute;
  background-color: white;
  border: 1px solid #ccc;
  min-width: 160px;
  z-index: 1;
  padding: 0.5rem 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}

.user-dropdown-content button {
  display: block;
  width: 100%;
  padding: 0.5rem 1rem;
  text-align: left;
  background: none;
  border: none;
  cursor: pointer;
}

.user-dropdown-content button:hover {
  background-color: #f0f0f0;
}
