# Hermes OS Architecture
Version: 0.1
---
# Philosophy
Hermes OS is designed as a modular decision-support system.
Every module has a single responsibility.
Every module can be replaced independently.
The system is built around transparency, testability and statistical validation.
---
# High-Level Architecture
                +--------------------+
                |   Data Provider    |
                +--------------------+
                          |
                          v
                +--------------------+
                | Market Observer    |
                +--------------------+
                          |
                          v
                +--------------------+
                | Trend Engine       |
                +--------------------+
                          |
                          v
                +--------------------+
                | Signal Engine      |
                +--------------------+
                          |
                          v
                +--------------------+
                | Risk Engine        |
                +--------------------+
                          |
                          v
                +--------------------+
                | Journal            |
                +--------------------+
                          |
                          v
                +--------------------+
                | Telegram Advisor   |
                +--------------------+
Research Lab works independently and analyzes historical data.
Behavior Engine analyzes trader actions instead of market data.
---
# Modules
## Data Provider
Responsibility:
Obtain market data.
Current implementation:
- T-Bank API
Future:
- Binance
- Bybit
- Interactive Brokers
Output:
Standard candle format.
The rest of the system never communicates directly with external APIs.
---
## Market Observer
Responsibility:
Transform raw market data into structured observations.
Examples:
- EMA50
- EMA200
- ATR
- ADX
- Volume
Output:
Market Snapshot
---
## Trend Engine
Responsibility:
Identify market phase.
Output:
Trend Score
Trend Direction
Market Phase
Confidence
The engine never generates trading signals.
---
## Signal Engine
Responsibility:
Generate trading opportunities.
Input:
Trend
Indicators
Rules
Output:
Long
Short
No Signal
---
## Risk Engine
Responsibility:
Position sizing
Stop Loss
Take Profit
Risk/Reward
Maximum portfolio risk
Daily risk limits
---
## Journal
Stores every decision.
Every signal.
Every rejected signal.
Every trade.
Every outcome.
Nothing is lost.
---
## Telegram Advisor
Daily reports.
Trade recommendations.
Risk information.
Reasoning.
No predictions.
---
## Research Lab
Runs historical experiments.
Tests hypotheses.
Produces statistics.
No production logic.
Research never changes production automatically.
---
## Behavior Engine
Tracks trader behavior.
Examples:
Rule violations
Stop movement
Manual intervention
Discipline score
This module evaluates the trader, not the market.
---
# Data Flow
Market Data
↓
Indicators
↓
Trend Analysis
↓
Signal Generation
↓
Risk Evaluation
↓
Decision
↓
Journal
↓
Telegram Report
---
# Design Principles
Single Responsibility
Every module has one job.
Loose Coupling
Modules should know as little as possible about each other.
Transparency
Every decision must be explainable.
Testability
Every module must be testable independently.
Replaceability
Any module can be replaced without rewriting the system.
---
# Project Layers
Infrastructure
External APIs
Storage
Telegram
Core
Indicators
Trend
Signals
Risk
Application
Workflow
Scheduler
Commands
Presentation
Telegram
CLI
Reports
Dashboard
---
# Future
Backtesting Engine
Machine Learning Experiments
Portfolio Management
Multiple Markets
Automatic Trading
Cloud Deployment
Web Dashboard
AI Research Assistant
---
# Guiding Principle
Hermes OS does not optimize profits.
Hermes OS optimizes decision quality.
