package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.mixins.fabric.AbstractContainerScreenAccess;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.Container;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;

/**
 * The agent's verbs' parts in 26.3 (PROTOCOL.md 8.5 and 8.7; SPEC.md 19.7 step 3b), as 1.7.10's: container.click, a
 * click on a slot of the open container's screen as the mouse's is (through the screen's own slotClicked, the game's
 * click packet included); block.items, the slots of the inventory at a block as the call's side holds them.
 */
final class FabricVerbs {

	/** container.click's modes, as 26.3's ContainerInput names them (1.7.10's window click types, in the same order). */
	private static final ContainerInput[] MODES = ContainerInput.values();
	private static final java.util.List<String> MODE_NAMES = java.util.Arrays.asList(
		"pickup", "quick_move", "swap", "clone", "throw", "quick_craft", "pickup_all");

	private FabricVerbs() {
	}

	static void bind(Probe probe) {
		probe.op("container.click").does(FabricVerbs::click).settles((call, value) -> FabricThings.waitClient(call, 2,
			value));
		probe.op("block.items").does(FabricVerbs::items);
	}

	/** container.click (8.5): NotReady without a container's screen; the slot's number in the open container. */
	private static JsonElement click(Call call) throws ProbeException {
		Screen screen = Minecraft.getInstance().gui.screen();
		if (!(screen instanceof AbstractContainerScreen<?> gui)) {
			throw new ProbeException("NotReady", "container.click needs a container's screen open, not "
				+ (screen == null ? "none" : screen.getClass().getName()), null);
		}
		AbstractContainerMenu menu = gui.getMenu();
		int size = menu.slots.size();
		if (!call.has("slot")) {
			throw ProbeException.badRequest("slot", "slot is a slot's number in the open container, 0 to " + (size - 1));
		}
		int index = (int) call.number("slot", 0, 0, size - 1);
		int button = (int) call.number("button", 0, 0, 8);
		String mode = call.string("mode", "pickup");
		int type = MODE_NAMES.indexOf(mode);
		if (type < 0) {
			throw ProbeException.badRequest("mode", "mode is one of " + MODE_NAMES + ", not " + mode);
		}
		((AbstractContainerScreenAccess) gui).unittas$slotClicked(menu.getSlot(index), index, button, MODES[type]);
		return new JsonObject();
	}

	/** block.items (8.7): NotFound where the block has no inventory. */
	private static JsonElement items(Call call) throws ProbeException {
		JsonElement given = call.args.get("pos");
		if (given == null || !given.isJsonArray() || given.getAsJsonArray().size() != 3) {
			throw ProbeException.badRequest("pos", "pos is [x, y, z]");
		}
		JsonArray at = given.getAsJsonArray();
		BlockPos pos = new BlockPos(at.get(0).getAsInt(), at.get(1).getAsInt(), at.get(2).getAsInt());
		Level level = FabricThings.player(call).level();
		BlockEntity tile = level.getBlockEntity(pos);
		if (!(tile instanceof Container inventory)) {
			String there = BuiltInRegistries.BLOCK.getKey(level.getBlockState(pos).getBlock()).toString();
			throw new ProbeException("NotFound", "no inventory at " + pos.getX() + ", " + pos.getY() + ", " + pos.getZ()
				+ ": " + there + " is there", Json.object("what", there));
		}
		JsonArray slots = new JsonArray();
		for (int i = 0; i < inventory.getContainerSize(); i++) {
			slots.add(FabricValues.item(inventory.getItem(i), level.registryAccess()));
		}
		return Json.object("slots", slots);
	}
}
