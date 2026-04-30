import pytest
from src.core.task_dispatcher import StrategyFactory, DefaultImageStrategy, FaceSwapStrategy, BaseVideoStrategy, LtxVideoStrategy
from src.constants import MODE_FACESWAP_STEP1, MODE_I2I_PRO

def test_strategy_factory_returns_correct_strategy():
    # Face swap
    strategy = StrategyFactory.get_strategy("face_swap")
    assert isinstance(strategy, FaceSwapStrategy)
    
    # LTX Video
    strategy = StrategyFactory.get_strategy("ltx_video")
    assert isinstance(strategy, LtxVideoStrategy)
    
    # Standard Video
    strategy = StrategyFactory.get_strategy("doggy_style")
    assert isinstance(strategy, BaseVideoStrategy)
    assert strategy.mode == "doggy_style"
    
    # I2I Pro (Default Image Strategy)
    strategy = StrategyFactory.get_strategy(MODE_I2I_PRO)
    assert isinstance(strategy, DefaultImageStrategy)
    assert strategy.mode == MODE_I2I_PRO
    
    # Default Image (fallback)
    strategy = StrategyFactory.get_strategy("unknown_mode")
    assert isinstance(strategy, DefaultImageStrategy)
    assert strategy.mode == "unknown_mode"

def test_video_strategy_cost_calculation():
    strategy = StrategyFactory.get_strategy("doggy_style")
    # Base doggy style cost is 6, 512p multiplier is 1.0, 5s multiplier is 1.0
    cost = strategy.get_cost({"resolution": "512p", "duration": "5s"})
    assert cost == 6
    
    # 720p base is 18, 5s multiplier is 1.0
    cost = strategy.get_cost({"resolution": "720p", "duration": "5s"})
    assert cost == 18
    
    # 720p base is 18, 8s multiplier is 2.0
    cost = strategy.get_cost({"resolution": "720p", "duration": "8s"})
    assert cost == 36
