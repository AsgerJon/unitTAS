package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import net.minecraft.client.gui.inventory.GuiContainerCreative;
import net.minecraft.init.Items;
import net.minecraft.item.ItemStack;

/**
 * The reset closes the client's container, not only its screen (EFR found it, 2026-11-04). The creative inventory keeps
 * window 0 as the client player's open container after its screen is gone, and the player's own slot updates then
 * land in its item grid: armour set on the server never reaches the client's feet. These two go together, in name
 * order, in one class on purpose: the client's container is the game's state, which a fresh world doesn't touch.
 */
@TasSuite("self")
public class ResetContainerTests extends TasTestCase {

	public void testA_leavesTheCreativeInventoryOpen() {
		onClient(() -> {
			mc().displayGuiScreen(new GuiContainerCreative(mc().thePlayer));
		});
		ticks(2);
		assertTrue(onClient(() -> mc().thePlayer.openContainer != mc().thePlayer.inventoryContainer),
			"the creative inventory didn't open its container");
	}

	public void testB_bootsReachTheClient() {
		String open = onClient(() -> mc().thePlayer.openContainer.getClass().getSimpleName());
		assertTrue(onClient(() -> mc().thePlayer.openContainer == mc().thePlayer.inventoryContainer),
			"the reset left the client's container open: " + open);
		onServer(() -> {
			player().setCurrentItemOrArmor(1, new ItemStack(Items.leather_boots));
			player().inventoryContainer.detectAndSendChanges();
		});
		waitUntilOnClient("the boots on the client's feet", () -> mc().thePlayer.getCurrentArmor(0) != null, 40);
	}
}
