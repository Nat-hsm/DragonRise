# DragonRise
DragonRise is a web application designed to promote and gamify stair climbing through a house-based point system. Users join one of six houses and log their stair-climbing activities to earn points for themselves and their house.

## Project Structure
dragonrise/
│
├── static/
│ ├── css/
│ │ └── style.css
│ └── images/
│ └── dragon-logo.png
│
├── templates/
│ ├── base.html
│ ├── dashboard.html
│ ├── index.html
│ ├── login.html
│ └── register.html
│
├── app.py
├── run.py
├── requirements.txt
└── README.md


## Features

### User Management
- User registration with house selection
- Secure login/logout functionality
- Personal dashboard for each user
- Individual point tracking
- Activity logging history

### House System
Six distinct houses to join:
- Black House
- Blue House
- Green House
- White House
- Gold House
- Purple House

### Points System
- Each flight of stairs = 10 points
- Points are awarded to:
  - Individual user total
  - House total points
- Real-time house rankings
- Tracking of total flights climbed

### Dashboard Features
- Personal statistics
  - Total flights climbed
  - Total points earned
  - House membership
- House rankings
- Quick climb logging
- Recent activity log

## Game Mechanics

### Point Accumulation
1. Users log their stair climbing activities
2. Points are calculated (flights × 10)
3. Points are simultaneously added to:
   - User's personal total
   - House's collective total

### House Competition
- Houses compete for the highest point total
- Real-time leaderboard updates
- Visible member count per house
- Collective house achievement tracking

### User Progress
- Individual progress tracking
- Personal statistics dashboard
- Activity history
- Contribution to house total

## Technical Details

### Dependencies

### Database Models

#### User
- Username (unique)
- Password (hashed)
- House affiliation
- Total flights
- Total points
- Join date
- Activity logs

#### House
- Name
- Total points
- Total flights
- Member count

#### ClimbLog
- User reference
- Flights climbed
- Points earned
- Timestamp
