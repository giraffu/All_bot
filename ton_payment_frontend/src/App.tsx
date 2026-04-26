import { useEffect, useState } from 'react'
import { TonConnectButton, useTonWallet, useTonConnectUI } from '@tonconnect/ui-react';
import WebApp from '@twa-dev/sdk'
import { beginCell } from '@ton/core'
import './App.css'

interface Plan {
  id: number;
  name: string;
  identity_name: string;
  original_price: number;
  final_price: number;
  reward_credits: number;
  duration_days: number;
  applied_rules: string[];
}

function App() {
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [paying, setPaying] = useState(false);
  const [loadingPlans, setLoadingPlans] = useState(true);

  const merchantAddress = import.meta.env.VITE_MERCHANT_ADDRESS;

  useEffect(() => {
    WebApp.ready();
    WebApp.expand();
    
    // Hardcoded plans for frontend-only approach
    const defaultPlans: Plan[] = [
      {
        id: 1,
        name: '基础月卡',
        identity_name: '内门弟子',
        original_price: 1.99,
        final_price: 1.99,
        reward_credits: 400,
        duration_days: 30,
        applied_rules: []
      },
      {
        id: 2,
        name: '高级月卡',
        identity_name: '核心弟子',
        original_price: 4.99,
        final_price: 4.99,
        reward_credits: 1200,
        duration_days: 30,
        applied_rules: []
      },
      {
        id: 3,
        name: '至尊月卡',
        identity_name: '真传弟子',
        original_price: 9.99,
        final_price: 9.99,
        reward_credits: 3000,
        duration_days: 30,
        applied_rules: []
      }
    ];
    
    setPlans(defaultPlans);
    setSelectedPlanId(defaultPlans[0].id);
    setLoadingPlans(false);
  }, []);

  const selectedPlan = plans.find(p => p.id === selectedPlanId);

  const handlePay = async () => {
    if (!selectedPlan) return;
    if (!merchantAddress) {
      WebApp.showAlert('未配置收款地址，请联系管理员');
      return;
    }
    
    if (!wallet) {
      tonConnectUI.openModal();
      return;
    }

    try {
      setPaying(true);
      
      const tgUserId = WebApp.initDataUnsafe?.user?.id;
      if (!tgUserId) {
        throw new Error('无法获取 Telegram 用户信息，请在 Telegram 内打开');
      }

      // Create payload: "ORDER:{tgUserId}:{planId}:{timestamp}"
      const orderId = `ORDER:${tgUserId}:${selectedPlan.id}:${Date.now()}`;
      
      // Build BOC payload with text comment
      const body = beginCell()
        .storeUint(0, 32) // Write 32 zero bits to indicate that a text comment will follow
        .storeStringTail(orderId) // Write our text comment
        .endCell();
        
      const payloadBoc = body.toBoc().toString("base64");

      // Calculate nanotons
      const amountNanotons = Math.floor(selectedPlan.final_price * 1e9).toString();

      // Send TON Transaction
      await tonConnectUI.sendTransaction({
        validUntil: Math.floor(Date.now() / 1000) + 600,
        messages: [
          {
            address: merchantAddress,
            amount: amountNanotons,
            payload: payloadBoc
          },
        ],
      });

      WebApp.showAlert('交易已发送！链上确认后，灵石将自动发放，请耐心等待（约 15-30 秒）。');
    } catch (err: any) {
      console.error(err);
      WebApp.showAlert(`支付失败或已取消: ${err.message || '未知错误'}`);
    } finally {
      setPaying(false);
    }
  };

  return (
    <div className="app-container theme-dark-gold">
      <header className="header">
        <h1>合欢宗账房</h1>
        <div className="wallet-section">
          <TonConnectButton />
        </div>
      </header>

      <main className="content">
        {loadingPlans ? (
          <div className="loading">加载中...</div>
        ) : (
          <>
            <section className="plans-section">
              <h2>选择修行套餐</h2>
              <div className="plans-grid">
                {plans.map(plan => (
                  <div 
                    key={plan.id} 
                    className={`plan-card ${selectedPlanId === plan.id ? 'selected' : ''}`}
                    onClick={() => setSelectedPlanId(plan.id)}
                  >
                    <div className="plan-name">{plan.name}</div>
                    <div className="plan-identity">{plan.identity_name}</div>
                    <div className="plan-credits">+{plan.reward_credits} 灵石</div>
                    <div className="plan-price">{plan.final_price} TON</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="comparison-section">
              <p className="note-text" style={{marginBottom: '15px', fontSize: '0.9em', color: '#aaa', textAlign: 'center'}}>
                <b>⚖️ 跨套餐升级/降级说明：若您当前套餐尚未过期，购买新套餐时，系统会自动计算老套餐剩余价值，并折算为新套餐的额外天数，保证您的权益不流失。</b>
              </p>
              <h2>权益对比</h2>
              <div className="comparison-table-wrapper">
                <table className="comparison-table">
                  <thead>
                    <tr>
                      <th>权益项目</th>
                      <th>内门弟子</th>
                      <th>核心弟子</th>
                      <th>真传弟子</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>💎 赠送永久灵石</td>
                      <td>400</td>
                      <td>1200</td>
                      <td>3000</td>
                    </tr>
                    <tr>
                      <td>📅 每日签到 (临时灵石)</td>
                      <td>+30/天</td>
                      <td>+45/天</td>
                      <td>+60/天</td>
                    </tr>
                    <tr>
                      <td>📺 解锁最高画质</td>
                      <td className="highlight-cell">720p</td>
                      <td colSpan={2} className="highlight-cell">
                        1024p
                      </td>
                    </tr>
                    <tr>
                      <td>⏳ 解锁最长时长</td>
                      <td className="highlight-cell">8s</td>
                      <td colSpan={2} className="highlight-cell">
                        10s
                      </td>
                    </tr>
                    <tr>
                      <td>🚀 基础排队优先级</td>
                      <td>
                        <b style={{color: 'var(--gold-primary)'}}>+15</b>
                      </td>
                      <td>
                        <b style={{color: 'var(--gold-primary)'}}>+25</b>
                      </td>
                      <td>
                        <b style={{color: '#ff4d4f'}}>+40 (极速)</b>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p className="note-text" style={{marginTop: '15px', fontSize: '0.9em', color: '#aaa', textAlign: 'center'}}>
                * 注：一点优先级约等于 1 分钟排队加速。为防霸占算力，优先级会随当日生成次数增加而动态衰减。
              </p>
            </section>
          </>
        )}
      </main>

      {selectedPlan && (
        <div className="fixed-bottom-bar">
          <button 
            className="pay-btn" 
            onClick={handlePay} 
            disabled={paying || loadingPlans}
          >
            {paying ? '处理中...' : `唤起 TON 钱包支付 ${selectedPlan.final_price} TON`}
          </button>
        </div>
      )}
    </div>
  )
}

export default App
