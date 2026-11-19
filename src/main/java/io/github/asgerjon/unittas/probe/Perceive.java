package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.block.Block;
import net.minecraft.client.Minecraft;
import net.minecraft.client.entity.EntityClientPlayerMP;
import net.minecraft.entity.EntityLivingBase;
import net.minecraft.util.AxisAlignedBB;
import net.minecraft.util.MathHelper;
import net.minecraft.util.MovingObjectPosition;
import net.minecraft.util.Vec3;
import net.minecraft.world.World;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * player.perceive (PROTOCOL.md 8.4, SPEC.md 15.6 step 1): what the client's player perceives now, for the agent's
 * brain in Python. Where it stands and how it moves, its own collision box, what its crosshair targets by the game's
 * own pick, its reach, and the blocks around it as the game collides with them. The probe says what is there; it
 * decides nothing.
 */
final class Perceive {

	/** 1.7.10's sideHit, by its number (ForgeDirection's order). */
	private static final String[] FACES = {"down", "up", "north", "south", "west", "east"};

	private Perceive() {
	}

	static void bind(Probe probe) {
		probe.op("player.perceive").does(Perceive::perceive);
	}

	private static JsonElement perceive(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getMinecraft();
		EntityClientPlayerMP player = mc.thePlayer;
		if (player == null || mc.theWorld == null) {
			throw new ProbeException("NotReady", "player.perceive needs a world", null);
		}
		int around = (int) call.number("around", 2, 0, 8);
		// how far below the feet's block and above the head's it looks, in blocks (terrain: SPEC.md 15.6 step 7)
		int below = (int) call.number("below", 1, 0, 8);
		int above = (int) call.number("above", 1, 0, 8);
		// the game's own pick, as runTick makes it each tick, for the look as it is now
		mc.entityRenderer.getMouseOver(1.0F);
		Vec3 eye = mc.renderViewEntity.getPosition(1.0F);
		float blockReach = mc.playerController.getBlockReachDistance();
		// the entity reach getMouseOver uses: 6 with creative's extended reach, otherwise 3 at most
		double entityReach = mc.playerController.extendedReach() ? 6.0 : Math.min(3.0, blockReach);
		return Json.object(
			"tick", Sides.get().ticks(Side.CLIENT),
			"pos", Values.pos(player),
			"eye", Arrays.asList(eye.xCoord, eye.yCoord, eye.zCoord),
			"box", box(player.boundingBox),
			"look", Values.look(player),
			"motion", Arrays.asList(player.motionX, player.motionY, player.motionZ),
			"on_ground", player.onGround,
			"collided", Json.object("horizontally", player.isCollidedHorizontally,
				"vertically", player.isCollidedVertically),
			"in_water", player.isInWater(),
			"in_lava", player.handleLavaMovement(),
			"on_ladder", player.isOnLadder(),
			"sneaking", player.isSneaking(),
			"sprinting", player.isSprinting(),
			"flying", player.capabilities.isFlying,
			"reach", Json.object("block", (double) blockReach, "entity", entityReach),
			// the rate the look turns at: none, as 1.7.10's probe has no mouse.rate (SPEC.md 19.7 step 12)
			"mouse_rate", Json.object("yaw", 0.0, "pitch", 0.0, "frames", 0),
			"target", target(mc.theWorld, mc.objectMouseOver),
			"blocks", around(mc.theWorld, player, around, below, above));
	}

	/** Whether a hand's click opens and shuts it: a wooden door, a fence gate, a wooden trapdoor (not iron's). */
	private static boolean opens(Block block) {
		boolean iron = block.getMaterial() == net.minecraft.block.material.Material.iron;
		return (block instanceof net.minecraft.block.BlockDoor || block instanceof net.minecraft.block.BlockTrapDoor) && !iron
			|| block instanceof net.minecraft.block.BlockFenceGate;
	}

	private static List<Double> box(AxisAlignedBB box) {
		return Arrays.asList(box.minX, box.minY, box.minZ, box.maxX, box.maxY, box.maxZ);
	}

	/** The crosshair's target, in player.use's shape (8.4) with what was hit; null when nothing is within reach. */
	private static JsonElement target(World world, MovingObjectPosition hit) {
		if (hit == null || hit.typeOfHit == MovingObjectPosition.MovingObjectType.MISS) {
			return null;
		}
		List<Double> at = Arrays.asList(hit.hitVec.xCoord, hit.hitVec.yCoord, hit.hitVec.zCoord);
		if (hit.typeOfHit == MovingObjectPosition.MovingObjectType.ENTITY) {
			return Json.object("entity", hit.entityHit.getEntityId(), "type", Values.type(hit.entityHit), "hit", at);
		}
		Block block = world.getBlock(hit.blockX, hit.blockY, hit.blockZ);
		return Json.object(
			"block", Arrays.asList(hit.blockX, hit.blockY, hit.blockZ),
			"face", FACES[hit.sideHit],
			"hit", at,
			"id", String.valueOf(Block.blockRegistry.getNameForObject(block)),
			"meta", world.getBlockMetadata(hit.blockX, hit.blockY, hit.blockZ));
	}

	/**
	 * The blocks that aren't air within 'reach' blocks of the feet's block across, from 'below' blocks below the feet's
	 * block to 'above' blocks above the head's (1 and 1, the default: the one below the feet to the one above the head):
	 * each with its collision boxes as the game gives them for this player (none for a flower), whether it is a liquid,
	 * whether the player can climb it, and whether a hand's click opens it (a wooden door, a fence gate).
	 */
	private static List<Object> around(World world, EntityLivingBase player, int reach, int below, int above) {
		List<Object> found = new ArrayList<>();
		int feetX = MathHelper.floor_double(player.posX);
		// the collision box's bottom, not posY less yOffset: that is the game's own feet, exactly
		int feetY = MathHelper.floor_double(player.boundingBox.minY);
		int feetZ = MathHelper.floor_double(player.posZ);
		for (int y = feetY - below; y <= feetY + 1 + above; y++) {
			for (int x = feetX - reach; x <= feetX + reach; x++) {
				for (int z = feetZ - reach; z <= feetZ + reach; z++) {
					Block block = world.getBlock(x, y, z);
					if (block.isAir(world, x, y, z)) {
						continue;
					}
					List<AxisAlignedBB> boxes = new ArrayList<>();
					AxisAlignedBB mask = AxisAlignedBB.getBoundingBox(x - 1, y - 1, z - 1, x + 2, y + 2, z + 2);
					block.addCollisionBoxesToList(world, x, y, z, mask, boxes, player);
					List<Object> each = new ArrayList<>();
					for (AxisAlignedBB box : boxes) {
						each.add(box(box));
					}
					found.add(Json.object(
						"pos", Arrays.asList(x, y, z),
						"id", String.valueOf(Block.blockRegistry.getNameForObject(block)),
						"meta", world.getBlockMetadata(x, y, z),
						"boxes", each,
						"liquid", block.getMaterial().isLiquid(),
						"climbable", block.isLadder(world, x, y, z, player),
						"opens", opens(block)));
				}
			}
		}
		return found;
	}
}
